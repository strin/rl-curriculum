# code for value iteration algorithms, such as Q-learning, SARSA, etc.
# this refractors the old dqn.py module by decoupling agent and algorithms.
from pyrl.common import *
import pyrl.optimizers as optimizers
import pyrl.layers as layers
import pyrl.prob as prob
from pyrl.utils import Timer
from pyrl.tasks.task import Task
from pyrl.agents.agent import DQN
from pyrl.agents.agent import TabularVfunc
from pyrl.config import floatX, debug_flag

class ValueIterationSolver(object):
    '''
    Vanilla value iteration for tabular environment
    '''
    def __init__(self, task, vfunc = None, tol=1e-3):
        self.task = task
        self.num_states = task.get_num_states()
        self.gamma = task.gamma
        self.tol = tol
        if vfunc:
            self.vfunc = vfunc
        else:
            self.vfunc = TabularVfunc(self.num_states)

    def get_action(self, state):
        '''Returns the greedy action with respect to the current policy'''
        poss_actions = self.task.get_allowed_actions(state)

        # compute a^* = \argmax_{a} Q(s, a)
        best_action = None
        best_val = -float('inf')
        for action in poss_actions:
            ns_dist = self.task.next_state_distribution(state, action)

            val = 0.
            for ns, prob in ns_dist:
                val += prob * self.gamma * self.vfunc(ns)

            if val > best_val:
                best_action = action
                best_val = val
            elif val == best_val and random.random() < 0.5:
                best_action = action
                best_val = val

        return best_action

    def learn(self):
        ''' Performs value iteration on the MDP until convergence '''
        while True:
            # repeatedly perform the Bellman backup on each state
            # V_{i+1}(s) = \max_{a} \sum_{s' \in NS} T(s, a, s')[R(s, a, s') + \gamma V(s')]
            max_diff = 0.

            # TODO: Add priority sweeping for state in xrange(self.num_states):
            for state in self.task.env.get_valid_states():
                poss_actions = self.task.get_allowed_actions(state)

                best_val = 0.
                for idx, action in enumerate(poss_actions):
                    val = 0.
                    ns_dist = self.task.next_state_distribution(state, action)
                    for ns, prob in ns_dist:
                        val += prob * (self.task.get_reward(state, action, ns) +
                                       self.gamma * self.vfunc(ns))

                    if(idx == 0 or val > best_val):
                        best_val = val

                diff = abs(self.vfunc(state) - best_val)
                self.vfunc.update(state, best_val)

                if diff > max_diff:
                    max_diff = diff

            if max_diff < self.tol:
                break


class Qlearn(object):
    def __init__(self, qfunc, gamma=0.95, alpha=1., epsilon=0.05, mode='backward'):
        self.qfunc = qfunc
        self.gamma = gamma
        self.alpha = alpha
        self.epsilon = epsilon
        self.total_exp = 0
        self.mode = mode

    def copy(self):
        # copy dqn.
        qfunc = self.qfunc.copy()
        learner = Qlearn(qfunc, gamma=self.gamma, alpha=self.alpha, epsilon=self.epsilon)
        learner.total_exp = self.total_exp
        return learner

    def run(self, task, num_episodes=100, num_steps=float('inf'), tol=1e-4, callback=None):
        '''
        task: the task to run on.
        num_episodes: how many episodes to repeat at maximum.
        tol: tolerance in terms of reward signal.
        budget: how many total steps to take.
        '''
        total_steps = 0.
        cum_rewards = []

        for ei in range(num_episodes):
            task.reset()

            curr_state = task.curr_state

            steps = 0.
            cum_reward = 0.
            factor = 1.

            history = []

            while True:
                # TODO: Hack!
                if steps >= np.log(tol) / np.log(self.gamma):
                    # print 'Lying and tell the agent the episode is over!'
                    break

                if total_steps > num_steps:
                    break

                action = self.qfunc.get_action(curr_state, method='eps-greedy', epsilon=self.epsilon, valid_actions=task.valid_actions)
                reward = task.step(action)
                next_state = task.curr_state

                if callback:
                    callback(task)

                meta = {
                    'is_terminal': task.is_end(),
                    'next_valid_actions': task.valid_actions
                }
                history.append((curr_state, action, next_state, reward, meta))

                steps += 1
                total_steps += 1
                self.total_exp += 1

                cum_reward = cum_reward + factor * reward
                factor *= self.gamma

                if task.is_end():
                    break

                curr_state = next_state

            if self.mode == 'backward': # backward mode.
                _history = history[::-1]
            else: # forward mode.
                _history = history

            for (i, (state, action, next_state, reward, meta)) in enumerate(_history):
                curr_val = self.qfunc.get(state, action)
                if not curr_val:
                    curr_val = 0.
                curr_val *= (1. - self.alpha)
                next_valid_actions = meta['next_valid_actions']
                if i > 0:
                    new_val = -float('inf')
                    for a in next_valid_actions:
                        val = self.qfunc.get(next_state, a)
                        if val != None and val > new_val:
                            new_val = val
                    new_val *= self.gamma
                else:
                    new_val = 0.
                new_val += reward
                curr_val += self.alpha * new_val
                self.qfunc.set(state, action, curr_val)

            cum_rewards.append(cum_reward)
            if total_steps > num_steps:
                break

        task.reset()
        return np.mean(cum_rewards)


class QlearnReplay(object):
    '''
    traditional Qlearning except with experience replay.
    '''
    def __init__(self, qfunc, gamma=0.95, alpha=1., epsilon=0.05, memory_size=1000, minibatch_size=512):
        self.qfunc = qfunc
        self.gamma = gamma
        self.alpha = alpha
        self.epsilon = epsilon
        self.total_exp = 0

        self.memory_size = memory_size
        self.minibatch_size = minibatch_size
        self.experience = []
        self.exp_idx = 0

        # used for streaming updates
        self.last_state = None
        self.last_action = None

    def _add_to_experience(self, s, a, ns, r, nva):
        # TODO: improve experience replay mechanism by making it harder to
        # evict experiences with high td_error, for example
        # s, ns are state_vectors.
        # nva is a list of valid_actions at the next state.
        self.total_exp += 1
        if len(self.experience) < self.memory_size:
            self.experience.append((s, a, ns, r, nva))
        else:
            self.experience[self.exp_idx] = (s, a, ns, r, nva)
            self.exp_idx += 1
            if self.exp_idx >= self.memory_size:
                self.exp_idx = 0

    def _end_episode(self, reward):
        if self.last_state is not None:
            self._add_to_experience(self.last_state, self.last_action, None,
                                    reward, [])
            # self._update_net()
        self.last_state = None
        self.last_action = None

    def _learn(self, next_state, reward, next_valid_actions):
        '''
        need next_valid_actions to compute appropriate V = max_a Q(s', a).
        '''
        self._add_to_experience(self.last_state, self.last_action,
                                next_state, reward, next_valid_actions)

        samples = prob.choice(self.experience, self.minibatch_size, replace=True) # draw with replacement.

        for idx, sample in enumerate(samples):
            state, action, next_state, reward, nva = sample

            self.qfunc.table[state, action] *= (1 - self.alpha)

            if next_state is not None:
                self.qfunc.table[state, action] += self.alpha * (reward
                                            + self.gamma * np.max(self.qfunc.table[next_state, nva]))
            else:
                self.qfunc.table[state, action] += self.alpha * reward

    def copy(self):
        # copy dqn.
        qfunc = self.qfunc.copy()
        learner = Qlearn(qfunc, gamma=self.gamma, alpha=self.alpha, epsilon=self.epsilon)
        learner.total_exp = self.total_exp
        return learner

    def run(self, task, num_episodes=100, tol=1e-4, budget=None):
        '''
        task: the task to run on.
        num_episodes: how many episodes to repeat at maximum.
        tol: tolerance in terms of reward signal.
        budget: how many total steps to take.
        '''
        total_steps = 0.
        for ei in range(num_episodes):
            task.reset()

            curr_state = task.curr_state

            num_steps = 0.
            while True:
                # TODO: Hack!
                if num_steps >= np.log(tol) / np.log(self.gamma):
                    # print 'Lying and tell the agent the episode is over!'
                    break

                action = self.qfunc.get_action(curr_state, method='eps-greedy', epsilon=self.epsilon, valid_actions=task.valid_actions)
                reward = task.step(action)
                next_state = task.curr_state

                self.last_state = curr_state
                self.last_action = action

                num_steps += 1
                total_steps += 1

                if task.is_end():
                    self._end_episode(reward)
                    break
                else:
                    self._learn(next_state, reward, task.valid_actions)
                    curr_state = next_state

                if budget and num_steps >= budget:
                    break
        task.reset()


class DeepQlearn(object):
    '''
    DeepMind's deep Q learning algorithms.
    '''
    def __init__(self, dqn_mt, gamma=0.95, l2_reg=0.0, lr=1e-3,
               memory_size=250, minibatch_size=64,
               nn_num_batch=1, nn_num_iter=2, regularizer={},
               update_freq=1, target_freq=10, skip_frame=0,
               frames_per_action=4,
               exploration_kwargs={
                   'method': 'eps-greedy',
                   'epsilon': 0.1
               }):
        '''
        (TODO): task should be task info.
        we don't use all of task properties/methods here.
        only gamma and state dimension.
        and we allow task switching.
        '''
        self.dqn = dqn_mt
        self.dqn_frozen = dqn_mt.copy()
        self.l2_reg = floatX(l2_reg)
        self.lr = floatX(lr)
        self.target_freq = target_freq
        self.update_freq = update_freq
        self.memory_size = memory_size
        self.minibatch_size = minibatch_size
        self.gamma = floatX(gamma)
        self.regularizer = regularizer
        self.skip_frame = skip_frame
        self.exploration_kwargs = exploration_kwargs
        self.frames_per_action = frames_per_action

        # for now, keep experience as a list of tuples
        self.experience = []
        self.exp_idx = 0
        self.total_exp = 0

        # used for streaming updates
        self.last_state = None
        self.last_valid_actions = None
        self.last_action = None

        # params for nn optimization.
        self.nn_num_batch = nn_num_batch
        self.nn_num_iter = nn_num_iter

        # dianostics.
        self.diagnostics = {
            'nn-error': [] # training of neural network on mini-batches.
        }

        # compile back-propagtion network
        self._compile_bp()


    def copy(self):
        # copy dqn.
        dqn_mt = self.dqn.copy()
        learner = DeepQlearn(dqn_mt, self.gamma, self.l2_reg, self.lr, self.memory_size, self.minibatch_size)
        learner.experience = list(self.experience)
        learner.exp_idx = self.exp_idx
        learner.total_exp = self.total_exp
        learner.last_state = self.last_state
        learner.last_action = self.last_action
        learner._compile_bp()
        return learner


    def _compile_bp(self):
        states = self.dqn.states
        action_values = self.dqn.action_values
        params = self.dqn.params
        targets = T.vector('target')
        last_actions = T.lvector('action')

        # loss function.
        mse = layers.MSE(action_values[T.arange(action_values.shape[0]),
                            last_actions], targets)
        # l2 penalty.
        l2_penalty = 0.
        for param in params:
            l2_penalty += .5 * (param ** 2).sum()


        cost = mse + self.l2_reg * l2_penalty

        reg_vs = []
        # mimic dqn regularizer.
        reg = self.regularizer.get('dqn-q')
        if reg:
            print '[compile-dqn] [regularizer] mimic dqn'
            dqn = reg['dqn']
            param = reg['param']
            print float(param) * self.minibatch_size / self.memory_size
            prior_action_values = T.matrix('prior_avs')
            reg_vs.append(prior_action_values)
            # cost += float(param) * self.minibatch_size / (1 + self.total_exp) * T.mean(abs(action_values - prior_action_values))
            cost = cost / action_values.shape[1] + T.mean(T.sqr(action_values - prior_action_values))
            #cost_e = (T.sum((action_values - prior_action_values)**2)
            #       - T.sum((action_values[T.arange(action_values.shape[0]),
            #                                     last_actions]
            #             -  prior_action_values[T.arange(action_values.shape[0]),
            #                                    last_actions]
            #               )**2)
            #        ) / (action_values.shape[0] * action_values.shape[1])

            #cost = cost / action_values.shape[1] + cost_e

        # back propagation.
        updates = optimizers.Adam(cost, params, alpha=self.lr)

        td_errors = T.sqrt(mse)
        self.bprop = theano.function(inputs=[states, last_actions, targets] + reg_vs,
                                     outputs=td_errors, updates=updates,
                                     allow_input_downcast=True,
                                     on_unused_input='ignore')

    def _add_to_experience(self, s, a, ns, r, meta):
        # TODO: improve experience replay mechanism by making it harder to
        # evict experiences with high td_error, for example
        # s, ns are state_vectors.
        # nva is a list of valid_actions at the next state.
        self.total_exp += 1
        if len(self.experience) < self.memory_size:
            self.experience.append((s, a, ns, r, meta))
        else:
            self.experience[self.exp_idx] = (s, a, ns, r, meta)
            self.exp_idx += 1
            if self.exp_idx >= self.memory_size:
                self.exp_idx = 0


    def _update_net(self):
        '''
            sample from the memory dataset and perform gradient descent on
            (target - Q(s, a))^2
        '''
        # don't update the network until sufficient experience has been
        # accumulated
        # removing this might cause correlation for early samples. suggested to be used in curriculums.
        if self.total_exp < self.skip_frame:
            return
        if self.total_exp % self.update_freq:
            return
        #if len(self.experience) < self.memory_size:
        #    return
        for nn_bi in range(self.nn_num_batch):
            states = [None] * self.minibatch_size
            next_states = [None] * self.minibatch_size
            actions = np.zeros(self.minibatch_size, dtype=int)
            rewards = np.zeros(self.minibatch_size)
            nvas = []

            # sample and process minibatch
            # samples = random.sample(self.experience, self.minibatch_size) # draw without replacement.
            samples = prob.choice(self.experience, self.minibatch_size, replace=True) # draw with replacement.
            terminals = []
            for idx, sample in enumerate(samples):
                state, action, next_state, reward, meta = sample
                nva = meta['next_valid_actions']

                states[idx] = state
                actions[idx] = action
                rewards[idx] = reward
                nvas.append(nva)

                if next_state is not None:
                    next_states[idx] = next_state
                else:
                    next_states[idx] = state
                    terminals.append(idx)

            # convert states into tensor.
            states = np.array(states).astype(floatX)
            next_states = np.array(next_states).astype(floatX)

            # compute target reward + \gamma max_{a'} Q(ns, a')
            # Ensure target = reward when NEXT_STATE is terminal
            if self.target_freq > 0:
                next_qvals = self.dqn_frozen.fprop(next_states)
            else:
                next_qvals = self.dqn.fprop(next_states)

            use_DDQN = False
            next_vs = np.zeros(self.minibatch_size).astype(floatX)
            if use_DDQN: # double DQN.
                next_qvals_unfrozen = self.dqn.fprop(next_states)
                for idx in range(self.minibatch_size):
                    if idx not in terminals:
                        next_action_index = np.argmax(next_qvals_unfrozen[idx, nvas[idx]])
                        next_vs[idx] = next_qvals[idx, nvas[idx][next_action_index]]
            else:
                for idx in range(self.minibatch_size):
                    if idx not in terminals:
                        next_vs[idx] = np.max(next_qvals[idx, nvas[idx]])

            targets = rewards + self.gamma * next_vs

            #if (targets > 100.).any():
            #    print 'error, target > 1', targets
            #    print 'rewards', rewards
            #    print 'next_vs', next_vs

            # using regularization.
            reg_vs = []
            reg = self.regularizer.get('dqn-q')
            if reg:
                dqn = reg['dqn']
                #dqn_avs = dqn.fprop(states)
                dqn_avs = self.dqn_frozen.fprop(states)
                #dqn_avs = next_qvals
                #for idx in range(self.minibatch_size):
                #    if idx not in terminals:
                #        dqn_avs[idx, :] = 0.
                reg_vs.append(dqn_avs)



            ## diagnostics.
            #print 'targets', targets
            #print 'next_qvals', next_qvals
            #print 'pure prop', self.dqn.fprop(states)
            #print 'prop', self.dqn.fprop(states)[range(states.shape[0]), actions]
            #print 'actions', actions
            nn_error = []
            for nn_it in range(self.nn_num_iter):
                if debug_flag and self.target_freq and self.total_exp % self.target_freq == 0:
                    print 'value before\n', self.dqn.fprop(states)[range(self.minibatch_size), actions]
                error = self.bprop(states, actions, targets.flatten(), *reg_vs)
                if debug_flag and self.target_freq and self.total_exp % self.target_freq == 0:
                    print 'nn_it', nn_it, 'error', error
                    print 'value after\n', self.dqn.fprop(states)[range(self.minibatch_size), actions]
                    print 'targets\n', targets
                    #print 'dqn vs\n', self.dqn.fprop(states)
                    #print 'dqn avs\n', dqn_avs
                    print 'next_qvals\n', next_qvals
                    print 'rewards', rewards
                    print 'total_exp', self.total_exp
                nn_error.append(float(error))
            self.diagnostics['nn-error'].append(nn_error)


    def _learn(self, next_state, reward, next_valid_actions):
        '''
        need next_valid_actions to compute appropriate V = max_a Q(s', a).
        '''
        self._add_to_experience(self.last_state, self.last_action,
                                next_state, reward, next_valid_actions)
        self._update_net()


    def _end_episode(self, reward, meta):
        if self.last_state is not None:
            self._add_to_experience(self.last_state, self.last_action, None,
                                    reward, meta)
            # self._update_net()
        self.last_state = None
        self.last_action = None


    def get_action(self, curr_state, valid_actions):
        # using interpolation.
        reg = self.regularizer.get('dqn-uct')
        if reg:
            uct = reg['uct']
            av = self.dqn.av(curr_state)
            prev_av = reg['dqn'].av(curr_state)
            c = uct.count_s(curr_state)
            ratio = np.sqrt(1 / (1 + float(c)))
            final_av = prev_av * ratio + av * (1 - ratio)
            action = np.argmax(final_av)
            uct.visit(curr_state, action)
            self.last_valid_actions = valid_actions
            self.last_state = curr_state
            self.last_action = action
            return action

        # normal get_action.
        action = self.dqn.get_action(curr_state, valid_actions=valid_actions,
                                     **self.exploration_kwargs)
        #action = self.dqn.get_action(curr_state, valid_actions=valid_actions,
        #                             method='softmax', temperature=0.01)
        self.last_valid_actions = valid_actions
        self.last_state = curr_state
        self.last_action = action
        return action


    def send_feedback(self, reward, next_state, next_valid_actions, is_end):
        self.next_valid_actions = next_valid_actions

        if self.target_freq > 0 and self.total_exp % self.target_freq == 0: # update target network.
            ## strategy 1. simple pickling.
            #self.dqn_frozen = self.dqn.copy()
            ## strategy 2.copy parameters.
            for (name, layer) in self.dqn.model.items():
                source_params = layer.get_params()
                for param in self.dqn_frozen.model[name].params:
                    param.set_value(np.array(source_params[param.name], dtype=floatX)) # deep copy.

        meta = {
            'next_valid_actions': next_valid_actions
        }

        if next_state is None or is_end:
            self._end_episode(reward, meta)
        else:
            self._learn(next_state, reward, meta)


def compute_tabular_value(task, tol=1e-4):
    solver = ValueIterationSolver(task, tol=tol)
    solver.learn()
    return solver.vfunc.V

def eval_tabular_value(task, func):
    V = np.zeros(task.get_num_states())
    for state in range(task.get_num_states()):
        V[state] = func(state)
    return V

def compute_tabular_values(tasks, num_cores = 8):
    ''' take a list of tabular tasks, and return states x tasks value matrix.
    '''
    vals = map(compute_tabular_value, tasks)
    return np.transpose(np.array(vals))
