import casadi as cs
import dyn_sliding_pack


class DynamicPusherModel():
    def __init__(self, pbm:dyn_sliding_pack.params.DynPusherProblem) -> None:
        self.Nx = 8
        self.Nu = 6
        self.Np = 1
        self.Nz = 1

        self.x = cs.SX.sym('x', self.Nx)  # state vector
        self.u = cs.SX.sym('u', self.Nu)  # control vector
        self.p = cs.SX.sym('p', self.Np)  # parameter vector (final time)
        self.z = cs.SX.sym('z', self.Nz)  # auxiliary & slackness vector

        # r - position (state vector)
        __x_board = cs.SX.sym('x_board')
        __y_board = cs.SX.sym('y_board')
        __theta_board = cs.SX.sym('theta_board')
        __x_mass = cs.SX.sym('x_mass')
        __r = cs.veccat(__x_board, __y_board, __theta_board, __x_mass)

        # v - velocity (state vector)
        __dx_board = cs.SX.sym('dx_board')
        __dy_board = cs.SX.sym('dy_board')
        __dtheta_board = cs.SX.sym('dtheta_board')
        __dx_mass = cs.SX.sym('dx_mass')
        __v = cs.veccat(__dx_board, __dy_board, __dtheta_board, __dx_mass)

        __x = cs.veccat(__r, __v)

        # u - control (control vector)
        __f_norm = cs.SX.sym('f_norm')
        __f_tan_p = cs.SX.sym('f_tan+')
        __f_tan_m = cs.SX.sym('f_tan-')
        __f_pusher = cs.veccat(__f_norm, __f_tan_p, __f_tan_m)

        __d2x_board = cs.SX.sym('d2x_board')
        __d2y_board = cs.SX.sym('d2y_board')
        __d2theta_board = cs.SX.sym('d2theta_board')
        __a_board = cs.veccat(__d2x_board, __d2y_board, __d2theta_board)

        __u = cs.veccat(__f_pusher, __a_board)

        # p - parameter (parameter vector)
        __t_finish = cs.SX.sym('t_finish')
        __p = cs.veccat(__t_finish)

        # z - auxiliary & slackness (auxiliary & slackness vector)
        __lambda = cs.SX.sym('lambda')
        __z = cs.veccat(__lambda)

        # constants
        __kMass = pbm.system.m
        __kBoardWidth = pbm.system.l
        __kMaxForce = pbm.system.f_max
        __kMaxLinVel = pbm.system.v_max
        __kMaxAngVel = pbm.system.omega_max
        __kMaxLinAcc = pbm.system.a_max
        __kMaxAngAcc = pbm.system.beta_max

        __kPosInitial = pbm.traj.r0
        __kPosTerminal = pbm.traj.rf
        __kVelInitial = pbm.traj.v0
        __KVelTerminal = pbm.traj.vf
        __kMinTermTime = pbm.traj.tf_min
        __kMaxTermTime = pbm.traj.tf_max

        __kMuGround = pbm.env.mu_g
        __kMuBoard = pbm.env.mu_p
        __kGravity = pbm.env.g

        # symbols
        __sLsurf = dyn_sliding_pack.funcs.make_limit_surface_matrix_symbol(fx_max=__kMuGround*__kMass*__kGravity,\
                                                                           fy_max=__kMuGround*__kMass*__kGravity,\
                                                                           m_max=1e-5)
        __sRotB2G_2X2 = dyn_sliding_pack.funcs.make_rotation_matrix_symbol(__dtheta_board, 2)  # rotation matrix (from Board to Ground)
        __sVelMass2G = cs.vertcat(__dx_board, __dy_board) + cs.mtimes(__sRotB2G_2X2, cs.vertcat(0, __dtheta_board*__x_mass))  # slider velocity viewed in world frame
        __sFricGround2G = -cs.mtimes(cs.inv(__sLsurf)[:2,:2], __sVelMass2G)  # ground friction viewed in world frame
        __sFricGround2B = cs.mtimes(__sRotB2G_2X2.T, __sFricGround2G)  # ground friction viewed in pusher frame

        __sInerBoard2B = cs.vertcat(__kMass*(__dtheta_board**2)*__x_mass, -2*__kMass*__dtheta_board*__dx_mass) - \
                         cs.mtimes(__sRotB2G_2X2.T, __kMass*cs.vertcat(__d2x_board, __d2y_board))

        optimConfig = dyn_sliding_pack.params.DynPusherOptimizationConfig()

        # dynamics
        __d2x_mass = (1/__kMass) * ((__f_tan_p-__f_tan_m) + \
                                    __sFricGround2B[0] + \
                                    __sInerBoard2B[0])
        __f = cs.vertcat(__v, __a_board, __d2x_mass)

        # inequality path constraints (≤0)
        __ineq0 = -(__dx_mass + __lambda)
        __ineq1 = -(-__dx_mass + __lambda)
        __ineq2 = -(__kMuBoard * __f_norm - __f_tan_p - __f_tan_m)
        __g = cs.vertcat(__ineq0, __ineq1, __ineq2)

        # equality path constraints
        __d2y_mass = (1/__kMass) * (__f_norm + \
                                    __sFricGround2B[1] + \
                                    __sInerBoard2B[1])
        
        __cmpl0 = __f_tan_p * (__dx_mass + __lambda)
        __cmpl1 = __f_tan_m * (-__dx_mass + __lambda)
        __cmpl2 = __lambda * (__kMuBoard * __f_norm - __f_tan_p - __f_tan_m)
        __h = cs.vertcat(__d2y_mass, __cmpl0, __cmpl1, __cmpl2)

        # initial and terminal constraints
        __hi = cs.vertcat(__r - __kPosInitial, __v - __kVelInitial)
        __ht  =cs.vertcat(__r - __kPosTerminal, __v - __KVelTerminal)

        # variable symbols
        optimConfig.x = self.x
        optimConfig.u = self.u
        optimConfig.p = self.p
        optimConfig.z = self.z
        
        # TO configuration
        optimConfig.lbx = [-cs.inf, -cs.inf, -cs.inf, -__kBoardWidth/2, -__kMaxLinVel, -__kMaxLinVel, -__kMaxAngVel, -__kMaxLinVel]
        optimConfig.ubx = [cs.inf, cs.inf, cs.inf, __kBoardWidth/2, __kMaxLinVel, __kMaxLinVel, __kMaxAngVel, __kMaxLinVel]

        optimConfig.lbu = [0.0, 0.0, 0.0, -__kMaxLinAcc, -__kMaxLinAcc, -__kMaxAngAcc]
        optimConfig.ubu = [__kMaxForce, __kMaxForce, __kMaxForce, __kMaxLinAcc, __kMaxLinAcc, __kMaxAngAcc]

        optimConfig.lbp = [__kMinTermTime]
        optimConfig.ubp = [__kMaxTermTime]

        optimConfig.lbz = [0.0]
        optimConfig.ubz = [cs.inf]

        # terminal and path integral costs
        __phi = (__t_finish / __kMaxTermTime) ** 2
        __gamma = cs.norm_2(__u / optimConfig.ubu) ** 2

        optimConfig.phi = cs.Function('phi', [__x, __p], [__phi], ['x', 'p'], ['phi'])
        optimConfig.gamma = cs.Function('gamma', [__x, __u, __p], [__gamma], ['x', 'u', 'p'], ['gamma'])
        optimConfig.f = cs.Function('f', [__x, __u, __p], [__f], ['x', 'u', 'p'], ['f'])
        optimConfig.g = cs.Function('g', [__x, __u, __p, __z], [__g], ['x', 'u', 'p', 'z'], ['g'])
        optimConfig.h = cs.Function('h', [__x, __u, __p, __z], [__h], ['x', 'u', 'p', 'z'], ['h'])
        optimConfig.hi = cs.Function('hi', [__x, __u, __p], [__hi], ['x', 'u', 'p'], ['hi'])
        optimConfig.ht = cs.Function('ht', [__x, __u, __p], [__ht], ['x', 'u', 'p'], ['ht'])

        self.continuous_pbm = optimConfig