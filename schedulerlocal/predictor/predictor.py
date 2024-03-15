import tensorflow as tf
import numpy as np
import math, random, os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 
from statistics import mean, stdev
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, LSTM
from sklearn.metrics import mean_squared_error
# Determinism consideration
tf.random.set_seed(10)
tf.keras.utils.set_random_seed(10)
tf.config.experimental.enable_op_determinism()

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
        self.config    = "TODO"
        self.threshold = "TODO"

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

    def __is_quescient(self, data, debug = False):
        # TODO: check on enough data and/or last training timestamp?
        look_back = 1
        
        trainX, trainY, testX, testY = self.__format_data(data=data, look_back=look_back)
        train_score, test_score = self.__predict_and_score(trainX, trainY, testX, testY, look_back)

        print('Train Score: %.2f RMSE' % (train_score))
        print('Test Score: %.2f RMSE' % (test_score))

        abs_gap = np.abs(train_score - test_score)
        threshold_val = self.config*self.threshold
        is_stable = False
        if abs_gap < threshold_val:
            if debug: print("Considered stable", abs_gap, "<", threshold_val, "from config", self.config)
            is_stable = True
        else:
            if debug: print("Considered unstable", abs_gap, ">=", threshold_val, "from config", self.config)
            is_stable = False
        return is_stable

    def __format_data(self, data : list, look_back : int):
        # First, split into train and test data while pseudo-normalizing
        delimit  = math.floor((len(data)/3)*2) # 2/3
        normalized_data = self.__pseudo_normalize(data=data)
        data_old = normalized_data[:delimit] # 2/3 for training
        data_new = normalized_data[delimit:] # 1/3 for assessing
        # reshape into X=t and Y=t+1
        trainX, trainY = self.__create_dataset(data_old, look_back)
        testX, testY = self.__create_dataset(data_new, look_back)
        # reshape input to be [samples, time steps, features]
        trainX = np.reshape(trainX, (trainX.shape[0], 1, trainX.shape[1]))
        testX = np.reshape(testX, (testX.shape[0], 1, testX.shape[1]))
        return trainX, trainY, testX, testY

    def __predict_and_score(self, trainX, trainY, testX, testY, look_back):
        model = Sequential()
        model.add(LSTM(4, input_shape=(1, look_back)))
        model.add(Dense(1))
        model.compile(loss='mean_squared_error', optimizer='adam')
        model.fit(trainX, trainY, epochs=100, batch_size=1, verbose=2)
        # make predictions
        train_predict = model.predict(trainX)
        test_predict = model.predict(testX)
        # invert predictions
        train_predict = self.__pseudo_normalize(train_predict, rev=True)
        trainY = self.__pseudo_normalize([trainY], rev=True)
        test_predict = self.__pseudo_normalize(test_predict, rev=True)
        testY = self.__pseudo_normalize([testY], rev=True)
        # calculate root mean squared error
        train_score = np.sqrt(mean_squared_error(trainY[0], train_predict[:,0]))
        test_score = np.sqrt(mean_squared_error(testY[0], test_predict[:,0]))
        return train_score, test_score

    def __pseudo_normalize(self, data : list, rev : bool = False):
        if rev:
            return [value*self.config for value in data]
        return [value/self.config for value in data]

    def __create_dataset(self, dataset, look_back=1):
        """
        convert an array of values into a dataset matrix
        From https://machinelearningmastery.com/time-series-prediction-lstm-recurrent-neural-networks-python-keras/
        """
        dataX, dataY = [], []
        for i in range(len(dataset)-look_back-1):
            a = dataset[i:(i+look_back), 0]
            dataX.append(a)
            dataY.append(dataset[i + look_back, 0])
        return np.array(dataX), np.array(dataY)