from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from schedulerlocal.subset.subset import CpuElasticSubset

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
        self.cpu_count = kwargs['cpu_count']
        self.actors_priority = dict()
        self.actors          = list()
        self.actor_fallback  = None
        self.current_orders  = dict()

    def is_market_effective(self):
        """Return a boolean VM based on market mechanism being currently applied or not
        ----------

        Parameters
        ----------
        vm : DomainEntity
            The VM to consider

        Returns
        -------
        status : bool
            True if effective, False otherwise
        """
        allocation = 0
        for actor in self.actors:
            allocation += actor.get_allocation()
            
        if allocation > self.cpu_count:
            return True
        return False

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
        # Order list of actors based on priority
        index_to_insert = -1
        for index, actor in enumerate(self.actors):
            if self.actors_priority[actor] < priority:
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
                renter = self.__get_renter(requester=actor, quantity=self.current_orders[actor], to_ignore=removed_from_market)
                removed_from_market.append(actor)
        ## Clean orders
        self.current_orders.clear()

    def __get_renter(self, requester : CpuElasticSubset, quantity : int, to_ignore : list):
        """Find an appropriate renter for the resource request
        ----------

        Parameters
        ----------
        requester : Subset
            subset requesting the resources
        quantity : int
            Quantity requested (positive amount)
        to_ignore : list
            List of actors to exclude from candidate list
        """
        # First,  ask nicely
        # Second, ask authoritatively
        # Third,  steal from weakest
        fullfilled = False

        # First, Nicely
        for actor in reversed(self.actors): # Ordered from the low-priority to the high priority
            if (actor == requester) or (actor in to_ignore):
                continue
            if actor.get_available() >= quantity:
                #TODO re-allocate. But what about scarsed resources?
                pass
            
        if not fullfilled and (requester != self.actor_fallback):
            # TODO: use fallback
            pass