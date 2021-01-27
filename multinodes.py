import numpy as np
import matplotlib.pyplot as plt
from numpy.core.fromnumeric import shape
from scipy.stats import halfnorm, norm
from scipy.special import binom
from scipy.optimize import fsolve, brentq, least_squares
from cvxopt import matrix, solvers
from sympy import solve, Poly, Eq, Function, exp 

import resource, sys

from itertools import chain, combinations, product
from copy import copy, deepcopy
from multiprocessing import Pool, Queue, Manager


def powerset(iterable):
    s = list(iterable)
    return list( chain.from_iterable(combinations(s, r) for r in range(len(s)+1)) )
# SS = list(powerset(road_set))
# print(list(SS))


def psi(a, c, t, N):
    beq = np.zeros(N)
    Aeq = np.zeros(shape=(N,N**2))
    for i in range(N):
        beq[i] = np.sum( a[i,:] ) - np.sum( a[:,i] )
        
        Aeq_i = np.zeros(shape=(N,N))
        Aeq_i[:,i] = -1
        Aeq_i[i,:] = 1
        Aeq_i[i,i] = 0
        Aeq[i,:] = Aeq_i.flatten('F')
            
    Aub = -np.eye(N**2)
    bub = np.zeros(N**2)

    # solvers.options['show_progress'] = False
    result = solvers.lp(
        # c=matrix(c.flatten('F')*t.flatten('F')), 
        c=matrix((t+2*np.eye(N)).flatten('F')), 
        G=matrix(Aub), 
        h=matrix(bub), 
        A=matrix(Aeq), 
        b=matrix(beq), 
        solver='glpk',
        options={'glpk':{'msg_lev':'GLP_MSG_OFF'}}
    )
    
    res = np.asarray(result['x'])
    return res.reshape((N,N))


def service_rate(R, a, c, t, sigma, N):
    def F(c,r):
        # return r/(self.C+0.01)
        rv = halfnorm(c, sigma)
        # rv = norm( c+5, sigma )
        return rv.cdf(r)
    # print(R,a)
    a = (1-np.vectorize(F)(c, R))*a
    # return a + psi(a, c, t)
    res = a + psi(a, c, t, N)
    # print(res)
    return res

# MVA
def Thpt(M, mu_r, mu_n, pi_r, pi_n, pi):
    L_n = np.zeros(len(mu_n))

    D_r = 1/(mu_r+10e-6)
    TH = 1
    for m in range(M+1):
        D_n = (1 + L_n)/(mu_n+10e-6)
        TH = m/( np.sum(pi_n*D_n) + np.sum(pi_r*D_r) )
        # print(m, np.sum(pi_n*D_n) + np.sum(pi_r*D_r))
        L_n = pi_n*TH*D_n
        # L_r = pi_r*TH*D_r
    
    return TH*pi


def Net_sol(m, R, w, N):
    a = w['a']
    c = w['c']
    t = w['t']
    sigma = w['f']

    mu_ij_n = service_rate( R, a, c, t, sigma, N )
    if mu_ij_n.sum() == 0:
        res = {
            'TH': np.zeros(N**2),
            'mu_r': np.zeros(N*(N-1)),
            'mu_n': np.zeros(N),
            'pi': np.zeros(N**2)
        }
        return res

    pi_n = mu_ij_n.dot(np.ones(N))
    # p = mu_ij_n / pi_n[:, np.newaxis]
    pi_r = mu_ij_n[t!=-1]
    pi = np.concatenate( (pi_n,pi_r), axis=None )
    # pi /= np.sum(pi)
    # print(pi)
    mu_r = 1/t[t!=-1]
    mu_n = mu_ij_n.dot(np.ones(N))
    # print(mu_n, mu_r)
    # print(mu_n, mu_r)

    res = {
        'TH': Thpt(m, mu_r, mu_n, pi_r, pi_n, pi),
        'mu_r': mu_r,
        'mu_n': mu_n,
        'pi': pi
    }
    return res



def cost(m, w, R, N):
    res = Net_sol(m, R, w, N)

    TH = res['TH'][N:]
    return TH.dot( w['c'][w['c']!=-1] )

def v(U, m, w, R, N):
    w_u = deepcopy(w)
    a_u = np.zeros(shape=np.shape(w['a']))
    for u in U:
        i = int(u/10)-1
        j = int(u%10)-1
        a_u[i,j] = w['a'][i,j]
    w_u['a'] = a_u
    # print(U)
    return cost(m, w_u, R, N)





def Sh_ij(args):
    p_set = args['s']
    p = args['p']
    w = args['w']
    R = args['R']
    m = args['m']
    N = args['n']
    
    p_size = len(p_set)
    p_set.remove(p)
    SS = powerset(p_set)
    # SS_size = len(SS)

    # print(SS, p_set, p)

    Sh = 0
    for u in SS:
        u_l = list(u)
        coeff = binom(p_size-1, len(u_l))
        Sh += (v(u_l+[p], m, w, R, N) - v(u_l, m, w, R, N))/coeff

    # print('v', v(p_set+[p], m, w, R, N), Sh)
    
    res = {'p': p, 'v': Sh/p_size}
    return res


# res = Net_sol(m, R, w)
# thpt = res['TH']
# thpt_ij = thpt[ node_set.index(13) ]
# print(thpt)
# print(thpt[4:].dot(c[c!=-1].flatten('F')))
# price = Sh/thpt_ij

# print(price)


def phi(w, R):
    R_s = np.zeros(shape=(N,N))
    for i,p in enumerate(players):
        R_s[int(p/10)-1, int(p%10)-1] = R[i]

    process_pool = [ {'s': players, 'p': i, 'w': w, 'm': m, 'n': N, 'R': R_s} for i in players ]

    with Pool() as pool:
        res = pool.map( Sh_ij, process_pool )
    
    res_SS = Net_sol(m, R_s, w, N)
    Th_SS = res_SS['TH']
    prices =  [ p['v']/(Th_SS[ node_set.index(p['p']) ]+10e-6) for p in res ]
    return np.array(prices)


def T(R):
    return phi(w, R)-R


if __name__ == '__main__':

    a = np.array([ [0,0.6,2.1,1.4], [0,0,3.6,1.2], [0,0,0,0], [0,0,1,0] ])
    t = np.array([
            [-1,15,21,20],
            [14,-1,12,15],
            [21,12,-1,12],
            [19,15,12,-1]
        ])

    c = np.array([
            [-1,12.4,16.5,16.9],
            [8.5,-1,5.2,8.5],
            [16.2,5.1,-1,5],
            [17,9.6,3.9,-1]
        ])

    # print(arr)
    nei_set = [1,2,3,4]
    # node_com = combinations(node_set, 2)
    node_product = product(nei_set, nei_set)
    road_set = [ 10*n[0]+n[1] for n in node_product if n[1]!=n[0] ]
    node_set = nei_set+road_set


    N = len(nei_set)
    players = [12,13,14,23,24,43]
    m = 100

    w = {
        'a': a,
        'f': 10,
        'c': c,
        't': t
    }
    R_init = np.ones(len(players))
    # m = 100

    # players = [12,13,14,23,24,43]

    # print(phi(w, R))

    # R_f = fsolve(T, R_init)
    R_f = least_squares(T, R_init, bounds = (0, 100))

    # R_f = T( np.array( [12.40000014,  6.381263  ,  9.82054552,  0.99377401,  5.32556105, 1.6919091 ] ) )

    print(R_f)