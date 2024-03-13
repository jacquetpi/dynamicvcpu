import vowpalwabbit
import numpy as np
import math, random
from statistics import mean, stdev
from sklearn import datasets
from sklearn.model_selection import train_test_split
from vowpalwabbit.sklearn import (
    VW,
    VWClassifier,
    VWRegressor,
    tovw,
    VWMultiClassifier,
    VWRegressor,
)

class Predictor(object):
    """
    A Predictor is in charge to predict the next active resources
    ...


    Public Methods
    -------
    iterate()
        Deploy a VM to the appropriate CPU subset    
    """
    def __init__(self, **kwargs):
        pass
    
    def predict(self):
        raise ValueError('Not implemented')

class PredictorMax(Predictor):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def predict(self, data : list, recompute : bool = True):
        if not data: # Shoud not happen
            print('Warning, predict was called with no value')
            return 0
        return max(data)

class PredictorScrooge(Predictor):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.last_value  = None
        self.strike      = 5
        self.strike_bnds = (3,6)
        self.strike_step = 1

    def predict(self, data : list, recompute : bool = True):
        if (self.last_value is None) or recompute:
            if not data: # Shoud not happen
                print('Warning, predict was called with no value')
                return 0 # not defining it as last value to force recompute)
            self.__update_strike(data)
            self.last_value = mean(data) + self.strike * stdev(data)
        return self.last_value

    def __update_strike(self, data):
        updated_strike = self.strike
        if self.__is_quescient(data):
            updated_strike -= self.strike_step
        else:
            updated_strike += self.strike_step
        # Check bounds limitation
        if updated_strike < self.strike_bnds[0]: updated_strike = self.strike_bnds[0]
        if updated_strike > self.strike_bnds[1]: updated_strike = self.strike_bnds[1]
        self.strike = updated_strike

    def __is_quescient(self):
        return True
        # TODO