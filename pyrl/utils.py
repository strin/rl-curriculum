import numpy.random as npr
import numpy as np

def make_minibatch_x(data, batch_size, num_iter):
    '''
    assume data is a N x D matrix, this method creates mini-batches
    by draw each mini-batch with replacement from the data for num_iter runs.
    '''
    N = data.shape[0]
    D = data.shape[1]
    mini_batch = np.zeros((batch_size, D))
    assert batch_size <= N
    for it in range(num_iter):
        ind = npr.choice(range(N), size=batch_size, replace=True)
        mini_batch[:, :] = data[ind, :]
        yield mini_batch

def make_minibatch_x_y(data, targets, batch_size, num_iter):
    '''
    assume data is a N x D matrix, this method creates mini-batches
    by draw each mini-batch with replacement from the data for num_iter runs.
    '''
    N = data.shape[0]
    Np = targets.shape[0]
    D = data.shape[1]
    Dp = targets.shape[1]
    batch_shape = list(data.shape)
    batch_shape[0] = batch_size
    mini_batch = np.zeros(batch_shape)
    mini_batch_targets = np.zeros((batch_size, Dp))
    assert N == Np
    assert batch_size <= N
    for it in range(num_iter):
        ind = npr.choice(range(N), size=batch_size, replace=True)
        if len(mini_batch.shape) == 2: # matrix data.
            mini_batch[:, :] = data[ind, :]
        elif len(mini_batch.shape) == 4: # tensor data.
            mini_batch[:, :, :, :] = data[ind, :, :, :]
        mini_batch_targets[:, :] = targets[ind, :]
        yield mini_batch, mini_batch_targets