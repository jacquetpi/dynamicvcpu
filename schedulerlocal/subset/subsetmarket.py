from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from schedulerlocal.subset.subset import CpuElasticSubset

import schedulerlocal.node.cpusetutils as cpuset_utils
from schedulerlocal.domain.domainentity import DomainEntity
from math import ceil, floor

class SubsetMarket(object):
    """
    A subsetMarket is in charge of arbitration between subset regarding cores allocation
    ...

    Attributes
    ----------
    actors_priority : dict
        Market actors (the subset) associated to their priority
    actors : list
        List of actors sorted by in a descending order based on their priority
    actors_fallback : Actor
        Actor to borrow from when no resources are available
    current_orders : dict 

    Public Methods
    -------
    pass_order()
        Pass a quantity order (in term of resources needed) to the market
    execute_orders()
        Execute all orders stored
    """

    def __init__(self, **kwargs):
        self.subset_manager = kwargs['subset_manager']
        self.cpuset = kwargs['cpuset']
        self.actors_priority = dict()
        self.actors          = list()
        self.actor_fallback  = None
        self.current_orders  = dict()
        self.effective = None

    def is_market_effective(self, recompute : bool = True):
        """Return a boolean VM based on market mechanism being currently applied or not
        ----------

        Parameters
        ----------
        recompute : bool
            Force to recompute condition

        Returns
        -------
        status : bool
            True if effective, False otherwise
        """
        if (self.effective is None) or recompute:
            allocation = 0
            for actor in self.actors:
                allocation += actor.get_allocation()
                
            # Introduce a margin to avoid too frequent switch on low oversubscribed environment
            margin=1
            if self.effective == True:
                margin=0.8

            if allocation > (len(self.cpuset.get_cpu_list())*margin):
                self.effective = True
            else:
                self.effective = False

        return self.effective

    def get_default_resources(self):
        return self.cpuset.get_cpu_list()

    def register_actor(self, actor : CpuElasticSubset, priority : int):
        """Register an actor (associated to its priority) in the Market system
        ----------

        Parameters
        ----------
        actor : Subset
            subset to register in the Market
        priority : int
            Priority value (index, the higher, the more important it is)
        """
        if actor in self.actors: return

        # Order list of actors based on priority
        index_to_insert = -1
        for index, existing_actor in enumerate(self.actors):
            if self.actors_priority[existing_actor] < priority:
                index_to_insert = index
                break
        
        self.actors_priority[actor] = priority
        if index_to_insert < 0 :
            self.actors.append(actor)
        else:
            self.actors.insert(index_to_insert, actor)
        self.actor_fallback = self.actors[-1]

    def remove_actor(self, actor : CpuElasticSubset):
        """Remove an actor from the Market system
        ----------

        Parameters
        ----------
        actor : Subset
            subset to remove from the market
        """
        del self.actors_priority[actor]
        self.actors.remove(actor)
        if not self.actors:
            self.actor_fallback = None

    def pass_order(self, actor : CpuElasticSubset, request : int):
        """Register an order for the next market session
        ----------

        Parameters
        ----------
        actor : Subset
            subset passing the order
        request : int
            Resource requested (can be 0)
        """
        if actor in self.current_orders:
            raise ValueError('An order was already passed (but not executed) for this actor')
        self.current_orders[actor] = request

    def execute_orders(self):
        """Execute orders currently stored and clear them
        ----------

        Parameters
        ----------
        actor : Subset
            subset to remove from the market
        """
        removed_from_market = list()
        for actor in self.actors:  # Ordered from the high priority to the low-priority
            if (actor in self.current_orders and self.current_orders[actor]>0): #need core(s)
                print('MarketDebug: executing order', actor.oversubscription.perf, self.current_orders[actor])
                cpu_affected = self.__get_renters(requester=actor, quantity=self.current_orders[actor], to_ignore=removed_from_market)
                removed_from_market.append(actor)
                del self.current_orders[actor]
        ## Clean orders
        self.current_orders.clear()

    def reclaim_from_all(self, quantity : int, simulation : bool, requester : CpuElasticSubset = None):
        """Try to retrieve a specific resource quantity from subsets for given requester
        ----------

        Parameters
        ----------
        requester : Subset
            subset requesting the resources
        quantity : int
            Quantity requested (positive amount)
        simulation : bool
            Should resources be actually transfered or not

        Returns
        -------
        cpu_affected : List
            List of CPU affected
        """
        return self.__get_renters(requester=requester, quantity=quantity, to_ignore=list(), simulation=simulation)

    def __get_renters(self, requester : CpuElasticSubset, quantity : int, to_ignore : list, simulation : bool = False):
        """Find appropriate renter(s) for the resource request
        ----------

        Parameters
        ----------
        requester : Subset
            subset requesting the resources
        quantity : int
            Quantity requested (positive amount)
        to_ignore : list
            List of actors to exclude from candidate list
        simulation : bool
            Should resources be actually transfered or not

        Returns
        -------
        cpu_affected : List
            List of CPU affected
        """
        # First, check unallocated resources
        # Second, ask others subsets nicely
        # Third, steal from weakest neighbor
    
        count_to_reclaim = quantity
        cpu_affected = list()

        # First, check unallocated resources
        while True:
            candidates = self.subset_manager.get_available()
            if count_to_reclaim <= 0 or (not candidates):
                break
            
            distance_from = cpu_affected if requester is None else requester.get_res()
            closest = self.__get_ordered_cpu_list(list_to_sort=candidates, distance_from=distance_from)[0]

            cpu_affected.append(closest)
            count_to_reclaim -= 1
            if (not simulation) and (requester != None): requester.add_res(closest)

        if cpu_affected and (not simulation) and (requester != None): requester.sync_pinning()
        if count_to_reclaim <= 0: return cpu_affected
        
        # Second, ask neighbors nicely    
        for actor in reversed(self.actors): # Ordered from the low-priority to the high priority
            if (actor == requester) or (actor in to_ignore):
                continue

            if actor.oversubscription.get_available() >= 0:
                reclaim_from_specific_actor = min( actor.oversubscription.get_available(), count_to_reclaim)
                count_to_reclaim -= reclaim_from_specific_actor
                cpu_affected.extend(self.__transfer_resources(receiver=requester, sender=actor, amount=reclaim_from_specific_actor, simulation=simulation))

            if count_to_reclaim <= 0:
                break

        # Third, steal from weakest neighbor
        if (count_to_reclaim>0) and (requester != self.actor_fallback):
            let_to_fallback_at_least = self.actor_fallback.get_max_consumer_allocation()
            reclaim_from_fallback = min(self.actor_fallback.get_capacity()-let_to_fallback_at_least, count_to_reclaim)
            if reclaim_from_fallback>0:
                cpu_affected.extend(self.__transfer_resources(receiver=requester, sender=self.actor_fallback, amount=reclaim_from_fallback, simulation=simulation))
                count_to_reclaim -= reclaim_from_fallback

        return cpu_affected

    def __transfer_resources(self, receiver : CpuElasticSubset, sender : CpuElasticSubset, amount : int, simulation : bool = False):
        """Transfer resources between two subsets
        ----------

        Parameters
        ----------
        receiver : CpuElasticSubset
            subset receiving the resources
        sender : CpuElasticSubset
            subset requesting the resources
        amount : int
            Number of resources in transaction
        simulation : bool
            Should resources be actually transfered or not

        Returns
        -------
        cpu_affected : List
            List of CPU affected
        """
        cpu_affected = list()

        # Specific case, receiver is not created yet
        if receiver is None: 
            cpu_affected = sender.get_res()[-amount:]
            if not simulation:
                for cpu in cpu_affected: 
                    sender.remove_res(cpu)
                sender.sync_pinning()
            return cpu_affected

        # Generic case, choose from sender the closest core to receiver
        candidates_ordered = self.__get_ordered_cpu_list(list_to_sort=sender.get_res(), distance_from=receiver.get_res())
        for index, cpu in enumerate(candidates_ordered):
            if index >= amount:
                break
            cpu_affected.append(cpu)
            if not simulation:
                sender.remove_res(cpu)
                receiver.add_res(cpu)

        if not simulation: # avoid the sync in the loop
            sender.sync_pinning()
            receiver.sync_pinning()

        return cpu_affected

    def __get_ordered_cpu_list(self, list_to_sort : list, distance_from : list):
        cpuid_dict = {cpu.get_cpu_id():cpu for cpu in list_to_sort}
        candidates = cpuset_utils.get_cpus_with_weight(cpuset=self.cpuset, from_list=list_to_sort, to_list=distance_from, exclude_max=False, distance_max=50)
        return [cpuid_dict[cpuid] for cpuid, _ in sorted(candidates.items(), key=lambda item: item[1])]