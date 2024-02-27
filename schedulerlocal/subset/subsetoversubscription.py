from schedulerlocal.domain.domainentity import DomainEntity
from schedulerlocal.predictor.predictor import PredictorCsoaa, PredictorScrooge
from schedulerlocal.subset.subsetmarket import SubsetMarket
from math import ceil, floor
import os

class SubsetOversubscription(object):
    """
    A SubsetOversubscription class is in charge to apply a specific oversubscription mechanism to a given subset
    ...

    Public Methods
    -------
    get_available()
        Virtual resources available
    unused_resources_count()
        Return attributed physical resources which are unused
    get_additional_res_count_required_for_vm()
        Return count of additional physical resources needed to deploy a vm
    get_id()
        Return oversubscription id
    """
    def __init__(self, **kwargs):
        req_attributes = ['subset']
        for req_attribute in req_attributes:
            if req_attribute not in kwargs: raise ValueError('Missing required argument', req_attributes)
            setattr(self, req_attribute, kwargs[req_attribute])

    def get_available(self):
        """Return the number of virtual resources unused
        ----------

        Returns
        -------
        available : int
            count of available resources
        """
        raise NotImplementedError()

    def unused_resources_count(self):
        """Return attributed physical resources which are unused
        ----------

        Returns
        -------
        unused : int
            count of unused resources
        """
        raise NotImplementedError()

    def get_id(self):
        """Return the oversubscription strategy ID
        ----------

        Returns
        -------
        id : str
           oversubscription id
        """
        raise NotImplementedError()

class SubsetOversubscriptionStatic(SubsetOversubscription):
    """
    A SubsetOversubscriptionStatic implements a static oversubscription mechanism (i.e. resource are oversubscribed by a fixed ratio)

    Attributes
    ----------
    ratio : float
        Static oversubscription ratio to apply
    critical_size : int
        VM will start being oversubscribed only after the number of VM reaches the critical_size attribute
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        req_attributes = ['ratio']
        for req_attribute in req_attributes:
            if req_attribute not in kwargs: raise ValueError('Missing required argument', req_attributes)
            setattr(self, req_attribute, kwargs[req_attribute])
        self.critical_size = 1

    def get_available(self, with_new_resources : int = 0):
        """Return the number of virtual resource available
        ----------

        Parameters
        ----------
        with_new_resources : int (opt)
            If a new VM is to be considered while computing if critical size is reached

        Returns
        -------
        available : int
            count of available resources
        """
        with_new_vm = False
        if with_new_resources>0:
            with_new_vm = True
        return self.get_oversubscribed_quantity(quantity=self.subset.get_capacity(), with_new_vm=with_new_vm) - self.subset.get_allocation()

    def get_oversubscribed_quantity(self, quantity : int, with_new_vm : bool = False):
        """Based on a specific quantity, return oversubscribed equivalent
        ----------

        Parameters
        ----------
        quantity : int
            Quantity to be oversubscribed
        with_new_vm : bool (opt)
            If a new VM is to be considered while computing if critical size is reached

        Returns
        -------
        quantity : int
            Quantity oversubscribed
        """
        return quantity*self.__get_effective_ratio(with_new_vm)

    def unused_resources_count(self):
        """Return attributed physical resources which are unused
        ----------

        Returns
        -------
        unused : int
            count of unused resources
        """
        available_oversubscribed = self.get_available()
        unused_cpu = floor(available_oversubscribed/self.__get_effective_ratio())

        used_cpu = self.subset.get_capacity() - unused_cpu

        # Test specific case: our unused count floor should not reduce the capacity below the maximum configuration observed
        # Avoid VM to be oversubscribed with themselves
        max_alloc = self.subset.get_max_consumer_allocation()
        if used_cpu < max_alloc: return max(0, floor(self.subset.get_capacity()-max_alloc))
    
        # Generic case
        return unused_cpu


    def get_additional_res_count_required_for_quantity(self, vm : DomainEntity, quantity : float):
        """Return the number of additional physical resource required to deploy specified vm. 
        0 if no additional resources is required
        ----------

        Parameters
        ----------
        vm : DomainEntity
            The VM being deployed
        quantity : float
            Quantity of resources on this oversubscription subset

        Returns
        -------
        missing : int
            number of missing physical resources
        """
        request    = quantity                   # Without oversubscription
        capacity   = self.subset.get_capacity() # Without oversubscription

        # Compute new resources needed based on oversubcription ratio
        available_oversubscribed = self.get_available()

        missing_oversubscribed   = (request - available_oversubscribed)
        missing_physical = ceil(missing_oversubscribed/self.__get_effective_ratio(with_new_vm=True)) if missing_oversubscribed > 0 else 0
        new_capacity = capacity + missing_physical

        # Check if new_capacity is enough to fullfil VM request without oversubscribing it with itself
        # E.g. a 32vCPU request should be in a pool with 32 physical CPU, no matter what others VM are in it.
        minimal_capacity = self.subset.get_max_consumer_allocation(additional_vm=vm, additional_vm_quantity=quantity)
        if new_capacity < minimal_capacity:
            missing_physical+= ceil(minimal_capacity-new_capacity)

        return missing_physical

    def get_id(self):
        """Return the oversubscription strategy ID
        ----------

        Returns
        -------
        id : str
           oversubscription id
        """
        return self.ratio

    def __get_effective_ratio(self, with_new_vm : bool = False):
        """Get oversubscription ratio to apply based on if critical size was reached or not
        ----------

        Parameters
        ----------
        with_new_vm : bool (opt)
            If a new VM is to be considered while computing if critical size is reached

        Returns
        -------
        ratio : float
           oversubscription
        """
        return self.ratio

    def is_critical_size_reached(self, with_new_vm : bool = False):
        """Verify if critical size was reached or not
        ----------

        Parameters
        ----------
        with_new_vm : bool (opt)
            If a new VM is to be considered while computing if critical size is reached

        Returns
        -------
        answer : bool
            True/False
        """
        count = self.subset.count_unique_consumer()
        if with_new_vm: count+=1
        return count >= self.critical_size

    def __str__(self):
        return 'static oc:' + str(self.ratio)


class SubsetOversubscriptionBasedOnPerf(SubsetOversubscription):
    """
    A SubsetOversubscriptionBasedOnPerf implements a dynamic oversubscription mechanism

    Attributes
    ----------
    ratio : float
        Static oversubscription ratio to apply
    critical_size : int
        VM will start being oversubscribed only after the number of VM reaches the critical_size attribute
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        req_attributes = []
        for req_attribute in req_attributes:
            if req_attribute not in kwargs: raise ValueError('Missing required argument', req_attributes)
            setattr(self, req_attribute, kwargs[req_attribute])
        self.predictor = PredictorScrooge()

    def register_market(self, market : SubsetMarket):
        self.market = market

    def get_market_request(self):
        if not self.market.is_market_effective():
            return 0

        peak = self.predictor.predict()
        peak_with_constraint =  peak*(1+(self.ratio/100))
        request = 0
        if peak_with_constraint < self.subset.count_res():
            request = peak_with_constraint - self.subset.count_res()
        return request

    def get_available(self, with_new_resources : int  = 0):
        """Return the number of virtual resource available. May be negative
        ----------

        Parameters
        ----------
        with_new_resources : int (opt)
            If a new VM is to be considered while computing if critical size is reached

        Returns
        -------
        available : int
            count of available resources
        """
        if(not self.market.is_market_effective()):
            return self.subset.count_res() - self.subset.get_allocation()
        return self.subset.count_res() - (1+(self.ratio/100))*self.predictor.predict()

    def get_additional_res_count_required_for_quantity(self, vm : DomainEntity, quantity : float):
        """Return the number of additional physical resource required to deploy specified vm. 
        0 if no additional resources is required
        ----------

        Parameters
        ----------
        vm : DomainEntity
            The VM being deployed
        quantity : float
            Quantity of resources on this oversubscription subset

        Returns
        -------
        missing : int
            number of missing physical resources
        """
        request    = quantity                   # Without oversubscription
        capacity   = self.subset.get_capacity() # Without oversubscription

        # TODO: computation based on predict
        return 1

        new_capacity = capacity + missing_physical

        # Check if new_capacity is enough to fullfil VM request without oversubscribing it with itself
        # E.g. a 32vCPU request should be in a pool with 32 physical CPU, no matter what others VM are in it.
        minimal_capacity = self.subset.get_max_consumer_allocation(additional_vm=vm, additional_vm_quantity=quantity)
        if new_capacity < minimal_capacity:
            missing_physical+= ceil(minimal_capacity-new_capacity)

        return missing_physical

    def get_id(self):
        """Return the oversubscription strategy ID
        ----------

        Returns
        -------
        id : str
           oversubscription id
        """
        return 'dynamic'


    def __str__(self):
        return 'perf oc:'