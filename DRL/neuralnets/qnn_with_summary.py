# coding: utf-8
import numpy as np
from ..utils import settings

def critere_keys(key, minus=False):
    """
    Return True if the key corresponds to a weight or a bias
    Parameters:
        key: string
        minus: Boolean, If true, critere_keys returns True if the key corresponds 
               to a parameter of theta minus, else, it returns True for a parameter of theta
    """
    critere = (key not in ["input_observation", "y_true", "y_action", "y", "y_minus"])
    critere = critere & (key[-3:] != "_ph") & (key[-7:] != "_assign")

    if minus:
        critere = critere & (key[-6:] == "_minus")
    else:
        critere = critere & (key[-6:] != "_minus")

    return critere


class QNeuralNetwork():
    """
    Class coding a Neural Network which evaluates the reward. In input, it will take a state (variable 
        observations) and will return the reward estimated for each action.
    """

    def __init__(self, input_size=4, output_size=2, n_hidden=2, hidden_size=[128, 64], 
                learning_rate=0.001, alpha_reg=0., beta_reg=0.01):
        """
        Parameters:
            input_size: size of observations, only 1D array are accepted for now
            output_size: number of possible action
            n_hidden: number of hidden layers, must be stricly positiv
            hidden_size: list of size of the hidden layers
            learning_rate: learning_rate used in the RMSPROP
            alpha_reg: coefficient of l1 regularisation
            beta_reg: coefficient of l2 regularisation
        """

        self.input_size = input_size
        self.output_size = output_size
        self.n_hidden = n_hidden
        self.hidden_size = hidden_size

        assert (self.n_hidden == len(self.hidden_size)), "Ill defined hidden layers"
        assert (self.n_hidden > 0), "Not implemented yet"

        self.variables = {}
        self.initialised = False
        self.learning_rate = learning_rate
        self.alpha_reg = alpha_reg
        self.beta_reg = beta_reg

        self.theta_copy = []

    def initialisation(self, sess):
        """
        Create the neural network, the loss and the train step
        """
        self.create_variables(name="")
        self.create_variables(name="_minus")
        self.create_placeholders()
        self.build_model(name="")
        self.build_model(name="_minus")
        self.reset_lr(None, True)
        self.build_loss()
        self.initialised = True
        # self.create_summary(sess)

    def create_summary(self, sess):
        import tensorflow as tf

        tf.summary.scalar("learning rate", self.decay_learning_rate)
        tf.summary.scalar("loss", self.loss)
        self.merged = tf.summary.merge_all()
        self.writer = tf.summary.FileWriter('./callbacks/summaries/', sess.graph)

    def create_weight_variable(self, shape, name="W"):
        """
        Create a matrix of weights as a tf variable. Create also a placeholder and a assign operation
        to change it value.
        Parameters:
            shape: 2-uple, size of the matrix
            name: name under which the variable is saved
        """
        import tensorflow as tf

        self.variables[name] = tf.Variable(tf.truncated_normal(shape, stddev=0.1), name=name)
        self.variables[name + "_ph"] = tf.placeholder(tf.float32, shape=shape, 
            name=name+"_ph")
        self.variables[name + "_assign"] = tf.assign(self.variables[name], 
            self.variables[name + "_ph"])

    def create_bias_variable(self, shape, name="b"):
        """
        Create a biais as a tf variable. Create also a placeholder and a assign operation
        to change it value.
        Parameters:
            shape: 2-uple, size of the biais
            name: name under which the variable is saved
        """
        import tensorflow as tf

        self.variables[name] = tf.Variable(tf.constant(0.1, shape=shape), name=name)
        self.variables[name + "_ph"] = tf.placeholder(tf.float32, shape=shape, 
            name=name+"_ph")
        self.variables[name + "_assign"] = tf.assign(self.variables[name], 
            self.variables[name + "_ph"])

    def create_variables(self, name=""):
        """
        Create all weight/biais variables for a full forward pass
        Parameters:
            name: string, used to complete every name of variables, usefull to create two NNs
        """
        self.create_weight_variable([self.input_size, self.hidden_size[0]], name="W1" + name)

        self.create_bias_variable((1, self.hidden_size[0]), name="b1" + name)

        for i in range(self.n_hidden-1):
            self.create_weight_variable([self.hidden_size[i], self.hidden_size[i+1]], 
                                        name="W"+str(i+2) + name)

            self.create_bias_variable((1, self.hidden_size[i+1]), name="b"+str(i+2) + name)


        self.create_weight_variable([self.hidden_size[-1], self.output_size], name="Wo" + name)

        self.create_bias_variable((1, self.output_size), name="bo" + name)

    def create_placeholders(self):
        """
        Create placeholders for the observations, the results and the actions took
        """
        import tensorflow as tf

        self.variables["input_observation"] = tf.placeholder(tf.float32, 
            shape=[None, self.input_size], name="i_observation")

        self.variables["y_true"] = tf.placeholder(tf.float32, shape=[None], name="y_true")

        self.variables["y_action"] = tf.placeholder(tf.float32, shape=[None, self.output_size], 
            name="action")

    def build_model(self, name=""):
        """
        Create the forward pass
        Parameters:
            name:String, name used in create_variables
        """
        import tensorflow as tf
        
        y = tf.nn.relu(tf.matmul(self.variables["input_observation"], self.variables["W1" + name]) + 
                       self.variables["b1" + name], name="y1"+name)
        
        for i in range(self.n_hidden-1):
            y = tf.nn.relu(tf.matmul(y, self.variables["W"+str(i+2)+name]) + 
                           self.variables["b"+str(i+2)+name], name="y"+str(i+2)+name)
        
        self.variables["y"+name] = tf.matmul(y, self.variables["Wo"+name]) + self.variables["bo"+name]

    def build_loss(self):
        """
        Create the node for the loss, and it's reduction
        """
        import tensorflow as tf

        y_1d = tf.reduce_sum(tf.multiply(self.variables["y"], self.variables["y_action"]), axis=1)
        loss = tf.nn.l2_loss(y_1d - self.variables["y_true"])

        l1_reg = 0
        l2_reg = 0

        keys = sorted(self.variables.keys())
        keys = [ key for key in keys if critere_keys(key, minus=False) ]
        for key in keys:
            l1_reg += tf.reduce_sum(tf.abs(self.variables[key]))
            l2_reg += tf.nn.l2_loss(self.variables[key])

        self.loss = loss + self.alpha_reg * l1_reg + self.beta_reg * l2_reg

        self.train_step = tf.train.RMSPropOptimizer(self.decay_learning_rate,
            decay=0.99, momentum=0.5, centered=True).minimize(self.loss, global_step=self.global_step)

    def reset_lr(self, sess, init=False):
        import tensorflow as tf
        
        if init:
            self.global_step = tf.Variable(0, trainable=False)
            self.global_step_pl = tf.placeholder(tf.int32)
            self.global_step_assign = tf.assign(self.global_step, self.global_step_pl)

            self.decay_steps = tf.Variable(1, trainable=False)
            self.decay_steps_pl = tf.placeholder(tf.int32)
            self.decay_steps_assign = tf.assign(self.decay_steps, self.decay_steps_pl)
        else:
            print("Reset")
            temp = sess.run(self.decay_steps) * 2
            # sess.run(self.global_step_assign)
            sess.run(self.decay_steps_assign, feed_dict={self.decay_steps_pl: temp})
        
        self.decay_learning_rate = tf.train.exponential_decay(self.learning_rate,
            global_step=self.global_step, decay_steps=self.decay_steps, decay_rate=0.999)

    def get_reward(self, observation, sess):
        feed_dic = {self.variables["input_observation"]: observation.reshape((1, -1))}
        reward = np.squeeze(sess.run(self.variables["y"], feed_dict=feed_dic))
        return reward

    def best_choice(self, observation, sess):
        """
        Return the best action and the estimated reward for a given state
        Parameters:
            observation: np.array, state of the environnement
            sess: tensorflow session, allow multiprocessing
        """
        assert self.initialised, "This model must be initialised (self.initialisation())"
        reward = self.get_reward(observation, sess)

        return np.argmax(reward), np.max(reward)

    def weighted_choice(self, observation, sess):
        """
        Return a random action weighted by estimated reward
        Parameters:
            observation: np.array, state of the environnement
            sess: tensorflow session, allow multiprocessing
        """
        assert self.initialised, "This model must be initialised (self.initialisation())"
        reward = self.get_reward(observation, sess)

        cor = max(-min(reward), 0)
        reward = [i+cor for i in reward]
        proba = [i/np.sum(reward) for i in reward]
        action = np.random.choice(range(len(reward)), p=proba)
      
        return action, reward[action]

    def best_action(self, observation, sess, weighted=False):
        """
        Return the best action for a given state
        Parameters:
            observation: np.array, state of the environnement
            sess: tensorflow session, allow multiprocessing
            weighted: If True, return a random aciton weighted with estimated reward. 
                      Else, the best one.
        """
        if weighted:
            return self.weighted_choice(observation, sess)[0]
        else:
            return self.best_choice(observation, sess)[0]

    def best_reward(self, observation, sess, weighted=False):
        """
        Return the estimated reward for a given state
        Parameters:
            observation: np.array, state of the environnement
            sess: tensorflow session, allow multiprocessing
            weighted: If True, return a random aciton weighted with estimated reward. 
                      Else, the best one.
        """
        if weighted:
            return self.weighted_choice(observation, sess)[1]
        else:
            return self.best_choice(observation, sess)[1]

    def assign_value_to_theta(self, sess):
        """
        Assign the value of the NN weights to theta
        Parameters: 
            sess: tensorflow session, allow multiprocessing
        """
        import tensorflow as tf

        assert self.initialised, "This model must be initialised (self.initialisation())."

        keys = sorted(self.variables.keys())
        keys = [ key for key in keys if critere_keys(key, minus=False)]

        diff = 0
        for i, key in enumerate(keys):
            diff_temp = sess.run(self.variables[key]) - self.theta_copy[i]
            settings.l_theta[i] += diff_temp
            diff += np.linalg.norm(diff_temp)
        return diff
        
    def read_value_from_theta(self, sess):
        """
        Assign the value of theta to the weights of the NN
        Parameters: 
            sess: tensorflow session, allow multiprocessing
        """
        import tensorflow as tf

        assert self.initialised, "This model must be initialised (self.initialisation())."

        self.theta_copy = []
        keys = sorted(self.variables.keys())
        keys = [ key for key in keys if critere_keys(key, minus=False)]

        for i, key in enumerate(keys):
            self.theta_copy.append(settings.l_theta[i])
            feed_dict = {self.variables[key + "_ph"]: settings.l_theta[i]}
            sess.run(self.variables[key + "_assign"], feed_dict=feed_dict)

    def read_value_from_theta_minus(self, sess):
        """
        Assign the value of theta minus to the weights of the NN
        Parameters: 
            sess: tensorflow session, allow multiprocessing
        """
        import tensorflow as tf

        assert self.initialised, "This model must be initialised (self.initialisation())."
        
        keys = sorted(self.variables.keys())
        keys = [ key for key in keys if critere_keys(key, minus=True)]

        for i, key in enumerate(keys):
            feed_dict = {self.variables[key + "_ph"]: settings.l_theta_minus[i]}
            sess.run(self.variables[key + "_assign"], feed_dict=feed_dict)
