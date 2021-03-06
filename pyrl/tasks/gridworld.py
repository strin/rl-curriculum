from pyrl.tasks.task import Task

import random
import numpy as np
import matplotlib.pyplot as plt
import dill as pickle

class GridWorld(Task):
    ''' RL variant of gridworld where the dynamics and reward function are not
        fully observed

        Currently, this task is episodic. If an agent reaches one of the
        reward states, it receives the reward and is reset to a new starting
        location.
    '''
    N = (0, 1)
    E = (1, 0)
    W = (-1, 0)
    S = (0, -1)

    actions = [N, E, W, S]

    def __init__(self, grid, action_stoch, goal, rewards, wall_penalty, state_type=np.ndarray, time_penalty=-0.01):
        ''' grid is a 2D numpy array with 0 indicates where the agent
            can pass and 1 indicates an impermeable wall.

            action_stoch is the percentage of time
            environment makes a random transition
            '''
        self.grid = grid
        self.action_stoch = action_stoch
        self.state_type = state_type
        self.goal = dict(goal)
        self.free_pos = self._free_pos()
        self.curr_pos = random.choice(self.free_pos)
        self.hit_wall = False

        self.wall_penalty = wall_penalty
        self.rewards = dict(rewards)
        self.env = grid
        self.time_penalty = time_penalty

        # save initial state
        self.init_goal = dict(goal)
        self.init_rewards = dict(rewards)

        # start the game fresh.
        self.reset()


    def copy(self):
        return pickle.loads(pickle.dumps(self))


    def _free_pos(self):
        pos = []
        self.state_id = {}
        self.state_pos = {}
        state_num = 0
        w, h = self.grid.shape
        for i in xrange(w):
            for j in xrange(h):
                self.state_id[(i, j)] = state_num
                if self.grid[i][j] == 0. and (i, j) not in self.goal:
                    pos.append((i, j))
                self.state_pos[state_num] = (i, j)
                state_num += 1
        return pos

    def reset(self):
        # history.
        self.last_action = None
        self.last_state = None
        self.num_steps = 0
        self.cum_reward = 0

        # state.
        self.hit_wall = False
        self.curr_pos = random.choice(self.free_pos)
        self.goal = dict(self.init_goal)
        self.rewards = dict(self.init_rewards)
        (h, w) = self.grid.shape
        self.state_3d = np.zeros((3, h, w))
        self.state_3d[0, self.curr_pos[0], self.curr_pos[1]] = 1.
        for pos in self.goal:
            self.state_3d[1, pos[0], pos[1]] = 1.
        self.state_3d[2, :, :] = self.grid


    def set_to(self, task):
        # history.
        self.last_action = task.last_action
        self.last_state = np.array(task.last_state)
        self.num_steps = task.num_steps
        self.cum_reward = task.cum_reward

        # state.
        self.hit_wall = task.hit_wall
        self.curr_pos = task.curr_pos
        self.goal = dict(task.init_goal)
        self.rewards = dict(task.init_rewards)
        self.state_3d = np.array(task.state_3d)


    def yield_all_states(self, state_type=np.ndarray):
        '''
        generate all possible states
        '''
        (h, w) = self.grid.shape
        for pos in self._free_pos():
            if state_type == np.ndarray:
                state_3d = np.zeros((3, h, w))
                state_3d[0, pos[0], pos[1]] = 1.
                for goal_pos in self.goal:
                    state_3d[1, goal_pos[0], goal_pos[1]] = 1.
                state_3d[2, :, :] = self.grid
                yield (pos, state_3d)
            elif state_type == str: # TODO: encode grid.
                yield 'p' + str(pos) + 'g[' + ','.join([str(goal_pos) for
                            goal_pos in self.goal]) + ']'
            elif state_type == int:
                yield pos[0] * w + pos[1]


    @property
    def curr_state(self):
        '''
        state is a 3xHxW tensor [state, goal, wall]
        should deep copy the state as it will go into the experience buffer.
        '''
        if self.state_type == np.ndarray:
            return np.array(self.state_3d) # important: state_3d is mutable!
        else:
            return self.curr_state_id


    @property
    def curr_state_dict(self):
        '''
        return a dict representtion of the state.
        '''
        return {
            'raw_state': np.array([self.state_3d[0, :, :],
                                        np.zeros_like(self.state_3d[1, :, :]),
                                        self.state_3d[2, :, :]]), # state without goal
            'pos': np.array(self.state_3d[0, :, :]),
            'goal': np.array(self.state_3d[1, :, :]),
            'grid': np.array(self.state_3d[2, :, :])
        }


    @property
    def curr_state_id(self):
        '''
        return the id of the state representation
        '''
        return self.state_id[self.curr_pos]

    @property
    def num_states(self):
        w, h = self.grid.shape
        return w * h

    @property
    def state_shape(self):
        return self.state_3d.shape

    @property
    def shape(self):
        return self.grid.shape

    @property
    def num_actions(self):
        return len(self.actions)

    @property
    def valid_actions(self):
        return range(len(self.actions))

    def _move(self, state, act):
        return (state[0] + act[0], state[1] + act[1])

    def _out_of_bounds(self, state):
        return state[0] < 0 or state[0] >= self.grid.shape[0] or state[1] < 0 \
            or state[1] >= self.grid.shape[1]

    def _hit_wall(self, state):
        return self.state_3d[2, state[0], state[1]]

    def step(self, action):
        # record history.
        self.last_action = action
        self.last_state = self.curr_state

        # run step.
        reward = self.time_penalty

        # update state_3d matrix
        self.state_3d[0, self.curr_pos[0], self.curr_pos[1]] = 0.

        # compute new coordinate.
        if random.random() < self.action_stoch:
            tmp = self._move(self.curr_pos, random.choice(self.actions))
        else:
            tmp = self._move(self.curr_pos, self.actions[action])
        if not self._out_of_bounds(tmp):
            if self._hit_wall(tmp):
                self.hit_wall = True
            else:
                self.curr_pos = tmp


        # update state_3d matrix.
        self.state_3d[0, self.curr_pos[0], self.curr_pos[1]] = 1.

        # update goal.
        if self.curr_pos in self.goal:
            self.state_3d[1, self.curr_pos[0], self.curr_pos[1]] = 0.
            reward += float(self.rewards[self.curr_pos])
            if id(self.goal) != id(self.rewards):
                del self.goal[self.curr_pos]
            del self.rewards[self.curr_pos]

        self.cum_reward += reward
        self.num_steps += 1
        return reward

    def is_end(self):
        if self.wall_penalty == 'death' and self.hit_wall:
            return True
        return len(self.goal) == 0

    def visualize(self, fig = 1, fname = None, format='png', qval=None):
        fig = plt.figure(fig, figsize=(5,5))
        plt.clf()
        ax = fig.add_axes([0.0, 0.0, 1., 1.])
        plt.imshow(np.transpose(self.grid), interpolation='none', vmax=1.0, vmin=0.0, aspect='auto')
        for g in self.goal.keys():
            circle = plt.Circle(g, radius=.3, color='w')
            ax.add_artist(circle)
        # plot pacman.
        (x, y) = self.curr_pos
        y = self.grid.shape[0] - 1 - y
        x /= float(self.grid.shape[1])
        y /= float(self.grid.shape[0])
        axicon = fig.add_axes([x, y, 1. / self.grid.shape[1], 1. / self.grid.shape[0]])
        im = plt.imread(__file__[:__file__.rfind('/')] + '/pacman.png')
        res = axicon.imshow(im, interpolation='nearest')
        axicon.axis('off')
        # plot qval.
        if not qval is None:
            axicon = fig.add_axes([0.8, 0.8, 0.2, 0.2])
            axicon.bar(np.arange(self.num_actions) , list(qval), color='red')
            plt.ylim([0.0, 1.0])
            axicon.set_xticks(np.arange(self.num_actions) + 0.5)
            axicon.set_xticklabels(['S', 'E', 'W', 'N'])
            axicon.set_frame_on(False)
            axicon.set_autoscale_on(False)
            axicon.get_yaxis().set_visible(False)
            for tic in axicon.xaxis.get_major_ticks():
                tic.tick1On = tic.tick2On = False
            axicon.xaxis.label.set_color('white')
            axicon.tick_params(axis='x', colors='white')
            axicon.patch.set_facecolor('white')
            axicon.patch.set_alpha(0.1)
            #axicon.axis('off')

        ax.axis('off')
        if fname:
            plt.savefig(fname, format=format)
        else:
            plt.show()
        return res

    def __repr__(self):
        return str(self.curr_pos) + ' -> ' + ','.join([str(key) for key in self.goal.keys()])


class GridWorldFixedStart(GridWorld):
    def __init__(self, start_pos, grid, action_stoch, goal, rewards, wall_penalty, state_type, time_penalty=0.01):
        self.start_pos = start_pos
        GridWorld.__init__(self, grid, action_stoch, goal, rewards, wall_penalty, state_type, time_penalty=time_penalty)
        assert(start_pos in self.free_pos)

    def reset(self):
        GridWorld.reset(self)
        self.state_3d[0, self.curr_pos[0], self.curr_pos[1]] = 0.
        self.curr_pos = self.start_pos
        self.state_3d[0, self.curr_pos[0], self.curr_pos[1]] = 1.

    def __repr__(self):
        return str(self.start_pos) + ' -> ' + ','.join([str(key) for key in self.goal.keys()])


class GridWorldMultiGoal(GridWorld):
    '''
    A GridWorld task where the agent is asked to visit a sequence of tasks.
    A reward 1. is given only if the agent visited the goals in correct order and got to the last one.
    '''
    def __init__(self, start_pos, start_phase, grid, action_stoch, goals, wall_penalty=0., time_penalty=0.01):
        self.start_pos = start_pos
        self.start_phase = start_phase
        self.goals = goals
        assert(start_phase >= 0 and start_phase < len(goals))
        self.goal_tuple = goals[start_phase]
        self.phase = self.start_phase

        GridWorld.__init__(self, grid, action_stoch,
                {self.goal_tuple: 1.0}, rewards={self.goal_tuple: 1.},
                wall_penalty=wall_penalty, state_type=np.ndarray,
                time_penalty=time_penalty)

        assert(start_pos in self.free_pos)

    def reset(self):
        self.goal_tuple = self.goals[self.start_phase]
        self.phase = self.start_phase
        GridWorld.reset(self)
        self.state_3d[0, self.curr_pos[0], self.curr_pos[1]] = 0.
        self.curr_pos = self.start_pos
        self.state_3d[0, self.curr_pos[0], self.curr_pos[1]] = 1.

    def step(self, action):
        local_reward = GridWorld.step(self, action)
        if local_reward == 1.: # get to a goal.
            if self.phase == len(self.goals) - 1:
                return 1.
            else:
                self.state_3d[1, self.goal_tuple[0], self.goal_tuple[1]] = 0.
                self.phase += 1
                self.goal_tuple = self.goals[self.phase]
                self.goal = {self.goal_tuple: 1.}
                self.rewards = self.goal
                self.state_3d[1, self.goal_tuple[0], self.goal_tuple[1]] = 1.
        return 0.

    def visualize(self, fig=1, fname=None, format='png'):
        if fname == None:
            print 'phase = ', self.phase
        return GridWorld.visualize(self, fig=fig, fname=fname, format=format)

    @property
    def num_phases(self):
        return len(self.goals)

