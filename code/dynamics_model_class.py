# dynamics_model_class.py
# @author: Lisa Wang
# @created: Apr 25 2017
#
#===============================================================================
# DESCRIPTION:
# exports dynamics model class, allows training and predicts next observation
#
#===============================================================================
# CURRENT STATUS: In progress
#===============================================================================
# USAGE: from dynamics_model_class import *

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import datetime
import six
import tensorflow as tf
import tflearn
import numpy as np
import multiprocessing as mp
from multiprocessing.managers import BaseManager

from helpers import *
import utils
import dataset_utils as d_utils
import models_dict_utils
FLAGS = tf.flags.FLAGS

class DynamicsModel(object):

    def __init__(self, model_id, timesteps=1, dropout=1.0, output_dropout=1.0, load_checkpoint=False, use_sess=False):
        #print('Loading RNN dynamics model...')

        # if timesteps:
        #     # if provided as an argument, overwrite n_timesteps from the model
        #     n_timesteps = timesteps
        self._tfgraph = tf.Graph()
        self._sess = None
        #if use_sess:
        #    # use session
        #    self._sess = tf.Session(graph=self.tfgraph)
        
        with self._tfgraph.as_default():
            #tf.reset_default_graph()
            self.timesteps = timesteps
            self.model_dict = models_dict_utils.load_model_dict(model_id)
            if self.model_dict["architecture"] == 'default':
                self.net, self.hidden_1, self.hidden_2 = self._build_regression_lstm_net(n_timesteps=timesteps,
                                                                                     n_inputdim=self.model_dict["n_inputdim"],
                                                                                     n_hidden=self.model_dict["n_hidden"],
                                                                                     n_outputdim=self.model_dict["n_outputdim"],
                                                                                     dropout=dropout,
                                                                                     output_dropout=output_dropout)
            elif self.model_dict["architecture"] == 'simple':
                self.net, self.hidden_1, self.hidden_2 = self._build_regression_lstm_net2(n_timesteps=timesteps,
                                                                                     n_inputdim=self.model_dict["n_inputdim"],
                                                                                     n_hidden=self.model_dict["n_hidden"],
                                                                                     n_outputdim=self.model_dict["n_outputdim"],
                                                                                     dropout=dropout,
                                                                                     output_dropout=output_dropout)
            elif self.model_dict["architecture"] == 'gru':
                self.net, self.hidden_1, self.hidden_2 = self._build_regression_lstm_net_gru(n_timesteps=timesteps,
                                                                                     n_inputdim=self.model_dict["n_inputdim"],
                                                                                     n_hidden=self.model_dict["n_hidden"],
                                                                                     n_outputdim=self.model_dict["n_outputdim"],
                                                                                     dropout=dropout,
                                                                                     output_dropout=output_dropout)
            elif self.model_dict["architecture"] == 'grusimple':
                self.net, self.hidden_1, self.hidden_2 = self._build_regression_gru_net2(n_timesteps=timesteps,
                                                                                     n_inputdim=self.model_dict["n_inputdim"],
                                                                                     n_hidden=self.model_dict["n_hidden"],
                                                                                     n_outputdim=self.model_dict["n_outputdim"],
                                                                                     dropout=dropout,
                                                                                     output_dropout=output_dropout)
            else:
                assert(False)

            tensorboard_dir = '../tensorboard_logs/' + model_id + '/'
            checkpoint_dir = '../checkpoints/' + model_id + '/'
            checkpoint_path = checkpoint_dir + '_/'
            #print("Directory path for tensorboard summaries: {}".format(tensorboard_dir))
            #print("Checkpoint directory path: {}".format(checkpoint_dir))

            utils.check_if_path_exists_or_create(tensorboard_dir)
            utils.check_if_path_exists_or_create(checkpoint_dir)

            self._model = tflearn.DNN(self.net, tensorboard_verbose=0, tensorboard_dir=tensorboard_dir, \
                                    checkpoint_path=None, max_checkpoints=3)

            if load_checkpoint:
                checkpoint = tf.train.latest_checkpoint(checkpoint_dir)  # can be none of no checkpoint exists
                #print ("Checkpoint filename: " + checkpoint)
                if checkpoint:
                    self.model.load(checkpoint, weights_only=True, verbose=True)
                    #print('Checkpoint loaded.')
                else:
                    pass
                    #print('No checkpoint found. ')
            #print('Model loaded.')

    def _build_regression_lstm_net(self, n_timesteps=1, n_inputdim=None, n_hidden=None,
                                           n_outputdim=None, dropout=1.0):
        net = tflearn.input_data([None, n_timesteps, n_inputdim],dtype=tf.float32, name='input_data')
        output_mask = tflearn.input_data([None, n_timesteps, n_outputdim], dtype=tf.float32, name='output_mask')
        net, hidden_states_1 = tflearn.lstm(net, n_hidden, weights_init='xavier', return_seq=True, return_state=True, dropout=dropout, name="lstm_1")
        net, hidden_states_2 = tflearn.lstm(net, n_outputdim, weights_init='xavier', activation='sigmoid', return_seq=True, return_state=True, dropout=dropout, name="lstm_2")
        net = tf.stack(net, axis=1)
        net = net * output_mask
        net = tflearn.regression(net, optimizer='adam', learning_rate=0.0005,
                                 loss='mean_square') # mean square works; binary crossentropy does not work for some reason
        return net, hidden_states_1, hidden_states_2
    
    def _build_regression_lstm_net2(self, n_timesteps=1, n_inputdim=None, n_hidden=None,
                                           n_outputdim=None, dropout=1.0):
        # don't have 2 lstms, just have a shared output layer
        # this alternative doesn't seem to work as well
        net = tflearn.input_data([None, n_timesteps, n_inputdim],dtype=tf.float32, name='input_data')
        output_mask = tflearn.input_data([None, n_timesteps, n_outputdim], dtype=tf.float32, name='output_mask')
        net, hidden_states_1 = tflearn.lstm(net, n_hidden, weights_init='xavier', return_seq=True, return_state=True, dropout=dropout, name="lstm_1")
        net = [tflearn.fully_connected(net[i], n_outputdim, activation='sigmoid', weights_init='xavier', scope='output_shared', reuse=(i>0)) for i in six.moves.range(n_timesteps)]
        net = tf.stack(net, axis=1)
        net = net * output_mask
        net = tflearn.regression(net, optimizer='adam', learning_rate=0.0005,
                                 loss='mean_square') # mean square works
        return net, hidden_states_1, None

    def _build_regression_lstm_net_gru(self, n_timesteps=1, n_inputdim=None, n_hidden=None,
                                           n_outputdim=None, dropout=1.0):
        net = tflearn.input_data([None, n_timesteps, n_inputdim],dtype=tf.float32, name='input_data')
        output_mask = tflearn.input_data([None, n_timesteps, n_outputdim], dtype=tf.float32, name='output_mask')
        net, hidden_states_1 = tflearn.gru(net, n_hidden, weights_init='xavier', return_seq=True, return_state=True, dropout=dropout, name="gru_1")
        net, hidden_states_2 = tflearn.gru(net, n_outputdim, weights_init='xavier', activation='sigmoid', return_seq=True, return_state=True, dropout=dropout, name="gru_2")
        net = tf.stack(net, axis=1)
        net = net * output_mask
        net = tflearn.regression(net, optimizer='adam', learning_rate=0.0005,
                                 loss='mean_square') # mean square works
        return net, hidden_states_1, hidden_states_2
    
    def _build_regression_gru_net2(self, n_timesteps=1, n_inputdim=None, n_hidden=None,
                                           n_outputdim=None, dropout=1.0, output_dropout=1.0):
        # don't have 2 lstms, just have a shared output layer
        # this alternative doesn't seem to work as well
        net = tflearn.input_data([None, n_timesteps, n_inputdim],dtype=tf.float32, name='input_data')
        output_mask = tflearn.input_data([None, n_timesteps, n_outputdim], dtype=tf.float32, name='output_mask')
        net, hidden_states_1 = tflearn.gru(net, n_hidden, weights_init='xavier', return_seq=True, return_state=True, dropout=dropout, name="gru_1")
        # only add dropout to the outputs
        net = tflearn.dropout(net, output_dropout)
        net = [tflearn.fully_connected(net[i], n_outputdim, activation='sigmoid', weights_init='xavier', scope='output_shared', reuse=(i>0)) for i in six.moves.range(n_timesteps)]
        net = tf.stack(net, axis=1)
        net = net * output_mask
        net = tflearn.regression(net, optimizer='adam', learning_rate=0.0005,
                                 loss='mean_square') # mean square works
        return net, hidden_states_1, None
    
    def load(self, s):
        with self._tfgraph.as_default():
            #tf.reset_default_graph()
            self._model.load(s)
    
    def save(self, s):
        with self._tfgraph.as_default():
            #tf.reset_default_graph()
            self._model.save(s)

    def train(self, train_data, n_epoch=1, callbacks=[], shuffle=None, load_checkpoint=True, validation_set=0.1, batch_size=None):
        """

        :param train_data: tuple (input_data, output_mask, output_data)
        :param n_epoch: number of epochs to train for
        :param load_checkpoint: whether to train from checkpoint or from scratch
        :return:
        """
        with self._tfgraph.as_default():
            #tf.reset_default_graph()
            input_data, output_mask, output_data = train_data
            date_time_string = datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
            run_id = "{}".format(date_time_string)
            self._model.fit([input_data, output_mask], output_data, n_epoch=n_epoch, validation_set=validation_set, run_id=run_id, callbacks=callbacks, shuffle=shuffle, batch_size=batch_size)


    def predict(self, input_data):
        """
        :param input_data: of shape (n_samples, n_timesteps, n_inputdim).
        :return:
        """
        with self._tfgraph.as_default():
            n_samples, n_timesteps, n_inputdim = input_data.shape
            assert(n_inputdim == self.model_dict["n_inputdim"]), "input dimension of data doesn't match the model."
            n_outputdim = self.model_dict["n_outputdim"]
            output_mask = np.ones((n_samples, n_timesteps, n_outputdim))
            if n_timesteps < self.timesteps:  # pad inputs and mask
                padded_input = np.zeros((n_samples, self.timesteps, n_inputdim))
                padded_input[:, :n_timesteps, :] = input_data[:, :, :]
                input_data = padded_input
                padded_mask = np.zeros((n_samples, self.timesteps, n_outputdim))
                padded_mask[:,:n_timesteps,:] = output_mask[:,:,:]
                output_mask = padded_mask
            elif n_timesteps > self.timesteps: # truncate inputs and mask
                input_data = input_data[:, :self.timesteps, :]
                output_mask = output_mask[:, :self.timesteps, :]
            #tf.reset_default_graph()
            return self._model.predict([input_data, output_mask])
    
    def get_timesteps(self):
        return self.timesteps


class DMCManager(BaseManager):
    '''
    Allows to create DynamicsModel objects in a separate process.
    '''
    pass

DMCManager.register('DynamicsModel', DynamicsModel)

class RnnStudentSim(object):
    '''
    A model-based simulator for a student. Maintains its own internal hidden state.
    Currently model can be shared because only the history matters
    '''

    def __init__(self, model):
        self.model = model
        self.seq_max_len = model.get_timesteps()
        self.sequence = [] # will store up to seq_max_len
        pass


    def sample_observations(self):
        """
        Returns list of probabilities
        """
        # special case when self.sequence is empty
        if not self.sequence:
            return None
        else:
            # turns the list of input vectors, into a numpy matrix of shape (1, n_timesteps, 2*n_concepts)
            # We need the first dimension since the network expects a batch.
            rnn_input_sequence = np.expand_dims(np.array(self.sequence), axis=0)
            pred = self.model.predict(rnn_input_sequence)
            t = len(self.sequence)

            prob_success_action = pred[0][t-1]
            # observation is a probability
            return prob_success_action


    def advance_simulator(self, action, observation):
        '''
        Given next action and observation, advance the internal hidden state of the simulator.
        '''
        input = d_utils.convert_to_rnn_input(action, observation)
        if len(self.sequence) == self.seq_max_len:
            self.sequence = self.sequence[1:] + [input]
        else:
            self.sequence.append(input)


    def copy(self):
        '''
        Make a copy of the current simulator.

        '''
        sim_copy = RnnStudentSim(self.model)
        sim_copy.sequence = self.sequence[:] # deep copy
        return sim_copy

class RnnStudentSimMemEnsemble(object):
    '''
    A model-based simulator for a student. Maintains its own internal hidden state.
    Currently model can be shared because only the history matters
    Uses an ensemble of memoized models.
    '''

    def __init__(self, n_concepts, mem_arrays_list):
        self.n_concepts = n_concepts
        self.mem_arrays_list = mem_arrays_list
        self.seq_max_len = len(mem_arrays_list[0])-1
        # story the current state
        self.step = 0
        self.history_ix = 0


    def sample_observations(self):
        """
        Returns next probabilities
        """
        # special case when self.sequence is empty
        if self.step == 0:
            return None
        else:
            pred_list = []
            for mem_arrays in self.mem_arrays_list:
                pred_list.append(mem_arrays[self.step][self.history_ix,:])
            return np.mean(pred_list,axis=0)


    def advance_simulator(self, action, observation):
        '''
        Given next action and observation, advance the internal hidden state of the simulator.
        action is StudentAction
        observation is 0 or 1
        '''
        self.step += 1
        next_branch = action_ob_encode(self.n_concepts, action.concept, observation)
        self.history_ix = history_ix_append(self.n_concepts, self.history_ix, next_branch)


    def copy(self):
        '''
        Make a copy of the current simulator.
        '''
        sim_copy = RnnStudentSimMemEnsemble(self.n_concepts, self.mem_arrays_list)
        sim_copy.step = self.step
        sim_copy.history_ix = self.history_ix
        return sim_copy

class RnnStudentSimEnsemble(object):
    '''
    A model-based simulator for a student.
    It's an ensemble of many models and averages their predictions.
    '''

    def __init__(self, model_list):
        self.model_list = model_list
        self.seq_max_len = model_list[0].get_timesteps()
        self.sequence = [] # will store up to seq_max_len
        pass


    def sample_observations(self):
        """
        Returns list of probabilities
        """
        # special case when self.sequence is empty
        if not self.sequence:
            return None
        else:
            # turns the list of input vectors, into a numpy matrix of shape (1, n_timesteps, 2*n_concepts)
            # We need the first dimension since the network expects a batch.
            rnn_input_sequence = np.expand_dims(np.array(self.sequence), axis=0)
            t = len(self.sequence)
            
            # average the predictions
            pred_list = []
            for curr_model in self.model_list:
                pred_list.append(curr_model.predict(rnn_input_sequence)[0][t-1])
            
            prob_success_action = np.mean(pred_list,axis=0)
            #six.print_('prob success action shape {}'.format(prob_success_action.shape))
            
            # observation is a probability
            return prob_success_action


    def advance_simulator(self, action, observation):
        '''
        Given next action and observation, advance the internal hidden state of the simulator.
        '''
        input = d_utils.convert_to_rnn_input(action, observation)
        if len(self.sequence) == self.seq_max_len:
            self.sequence = self.sequence[1:] + [input]
        else:
            self.sequence.append(input)


    def copy(self):
        '''
        Make a copy of the current simulator.

        '''
        sim_copy = RnnStudentSimEnsemble(self.model_list) #list of models is shared
        sim_copy.sequence = self.sequence[:] # deep copy
        return sim_copy
