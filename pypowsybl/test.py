import math
import os

import pyoptinterface as poi
from pyoptinterface import nlfunc, ipopt
import pypowsybl as pp


def branch_flow(vars, params):
    G, B, Bc = params.G, params.B, params.Bc
    Vi, Vj, theta_i, theta_j, Pij, Qij, Pji, Qji = (
        vars.Vi,
        vars.Vj,
        vars.theta_i,
        vars.theta_j,
        vars.Pij,
        vars.Qij,
        vars.Pji,
        vars.Qji,
    )

    sin_ij = nlfunc.sin(theta_i - theta_j)
    cos_ij = nlfunc.cos(theta_i - theta_j)

    Pij_eq = G * Vi ** 2 - Vi * Vj * (G * cos_ij + B * sin_ij) - Pij
    Qij_eq = -(B + Bc) * Vi ** 2 - Vi * Vj * (G * sin_ij - B * cos_ij) - Qij
    Pji_eq = G * Vj ** 2 - Vi * Vj * (G * cos_ij - B * sin_ij) - Pji
    Qji_eq = -(B + Bc) * Vj ** 2 - Vi * Vj * (-G * sin_ij - B * cos_ij) - Qji

    return [Pij_eq, Qij_eq, Pji_eq, Qji_eq]


# pip install pyoptinterface llvmlite tccbox
#
# git clone https://github.com/coin-or-tools/ThirdParty-Mumps.git
# cd ThirdParty-Mumps
# ./get.Mumps
# ./configure --prefix $HOME/mumps
# make -j 8
# make install
#
# git clone https://github.com/coin-or/Ipopt
# cd Ipopt/
# ./configure --prefix $HOME/ipopt --with-mumps-cflags="-I$HOME/mumps/include/coin-or/mumps/" --with-mumps-lflags="-L$HOME/mumps/lib -lcoinmumps"
# make -j 8
# make install
#
# export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$HOME/mumps/lib:$HOME/ipopt/lib
#
if __name__ == "__main__":
    branches = [
        # (from, to, R, X, B, angmin, angmax, Smax)
        (0, 1, 0.00281, 0.0281, 0.00712, -30.0, 30.0, 4.00),
        (0, 3, 0.00304, 0.0304, 0.00658, -30.0, 30.0, 4.26),
        (0, 4, 0.00064, 0.0064, 0.03126, -30.0, 30.0, 4.26),
        (1, 2, 0.00108, 0.0108, 0.01852, -30.0, 30.0, 4.26),
        (2, 3, 0.00297, 0.0297, 0.00674, -30.0, 30.0, 4.26),
        (3, 4, 0.00297, 0.0297, 0.00674, -30.0, 30.0, 2.40),
    ]

    buses = [
        # (Pd, Qd, Gs, Bs, Vmin, Vmax)
        (0.0, 0.0000, 0.0, 0.0, 0.9, 1.1),
        (3.0, 0.9861, 0.0, 0.0, 0.9, 1.1),
        (3.0, 0.9861, 0.0, 0.0, 0.9, 1.1),
        (4.0, 1.3147, 0.0, 0.0, 0.9, 1.1),
        (0.0, 0.0000, 0.0, 0.0, 0.9, 1.1),
    ]

    generators = [
        # (bus, Pmin, Pmax, Qmin, Qmax, a, b, c)
        (0, 0.0, 0.4, -0.300, 0.300, 0.0, 1400, 0.0),
        (0, 0.0, 1.7, -1.275, 1.275, 0.0, 1500, 0.0),
        (2, 0.0, 5.2, -3.900, 3.900, 0.0, 3000, 0.0),
        (3, 0.0, 2.0, -1.500, 1.500, 0.0, 4000, 0.0),
        (4, 0.0, 6.0, -4.500, 4.500, 0.0, 1000, 0.0),
    ]

    import pandas as pd

    pd.options.display.max_columns = None
    pd.options.display.expand_frame_repr = False
    # n = pp.network.load("/home/jamgotchiangeo/cases/case5.mat")
    # print(n.get_lines())

    slack_bus = 3

    model = ipopt.Model()
    bf = model.register_function(branch_flow)
    N_branch = len(branches)
    N_bus = len(buses)
    N_gen = len(generators)

    # create variables and bounds
    Pbr_from = model.add_variables(range(N_branch))
    Qbr_from = model.add_variables(range(N_branch))
    Pbr_to = model.add_variables(range(N_branch))
    Qbr_to = model.add_variables(range(N_branch))

    V = model.add_variables(range(N_bus), name="V")
    theta = model.add_variables(range(N_bus), name="theta")

    for i in range(N_bus):
        Vmin, Vmax = buses[i][4], buses[i][5]
        model.set_variable_bounds(V[i], Vmin, Vmax)

    model.set_variable_bounds(theta[slack_bus], 0.0, 0.0)

    P = model.add_variables(range(N_gen), name="P")
    Q = model.add_variables(range(N_gen), name="Q")

    for i in range(N_gen):
        model.set_variable_bounds(P[i], generators[i][1], generators[i][2])
        model.set_variable_bounds(Q[i], generators[i][3], generators[i][4])

    # nonlinear constraints
    for k in range(N_branch):
        branch = branches[k]
        R, X, Bc2 = branch[2], branch[3], branch[4]

        G = R / (R ** 2 + X ** 2)
        B = -X / (R ** 2 + X ** 2)
        Bc = Bc2 / 2

        i = branch[0]
        j = branch[1]

        Vi = V[i]
        Vj = V[j]
        theta_i = theta[i]
        theta_j = theta[j]

        Pij = Pbr_from[k]
        Qij = Qbr_from[k]
        Pji = Pbr_to[k]
        Qji = Qbr_to[k]

        model.add_nl_constraint(
            bf,
            vars=nlfunc.Vars(
                Vi=Vi,
                Vj=Vj,
                theta_i=theta_i,
                theta_j=theta_j,
                Pij=Pij,
                Qij=Qij,
                Pji=Pji,
                Qji=Qji,
            ),
            params=nlfunc.Params(G=G, B=B, Bc=Bc),
            eq=0.0,
        )

    # power balance constraints
    P_balance_eq = [poi.ExprBuilder() for i in range(N_bus)]
    Q_balance_eq = [poi.ExprBuilder() for i in range(N_bus)]

    for b in range(N_bus):
        Pd, Qd = buses[b][0], buses[b][1]
        Gs, Bs = buses[b][2], buses[b][3]
        Vb = V[b]

    P_balance_eq[b] -= poi.quicksum(
        Pbr_from[k] for k in range(N_branch) if branches[k][0] == b
    )
    P_balance_eq[b] -= poi.quicksum(
        Pbr_to[k] for k in range(N_branch) if branches[k][1] == b
    )
    P_balance_eq[b] += poi.quicksum(P[i] for i in range(N_gen) if generators[i][0] == b)
    P_balance_eq[b] -= Pd
    P_balance_eq[b] -= Gs * Vb * Vb

    Q_balance_eq[b] -= poi.quicksum(
        Qbr_from[k] for k in range(N_branch) if branches[k][0] == b
    )
    Q_balance_eq[b] -= poi.quicksum(
        Qbr_to[k] for k in range(N_branch) if branches[k][1] == b
    )
    Q_balance_eq[b] += poi.quicksum(Q[i] for i in range(N_gen) if generators[i][0] == b)
    Q_balance_eq[b] -= Qd
    Q_balance_eq[b] += Bs * Vb * Vb

    model.add_quadratic_constraint(P_balance_eq[b], poi.Eq, 0.0)
    model.add_quadratic_constraint(Q_balance_eq[b], poi.Eq, 0.0)

    for k in range(N_branch):
        branch = branches[k]

        i = branch[0]
        j = branch[1]

        theta_i = theta[i]
        theta_j = theta[j]

        angmin = branch[5] / 180 * math.pi
        angmax = branch[6] / 180 * math.pi

        model.add_linear_constraint(theta_i - theta_j, poi.In, angmin, angmax)

        Smax = branch[7]
        Pij = Pbr_from[k]
        Qij = Qbr_from[k]
        Pji = Pbr_to[k]
        Qji = Qbr_to[k]
        model.add_quadratic_constraint(Pij * Pij + Qij * Qij, poi.Leq, Smax * Smax)
        model.add_quadratic_constraint(Pji * Pji + Qji * Qji, poi.Leq, Smax * Smax)

    cost = poi.ExprBuilder()
    for i in range(N_gen):
        a, b, c = generators[i][5], generators[i][6], generators[i][7]
        cost += a * P[i] * P[i] + b * P[i] + c
    model.set_objective(cost)

    model.optimize()

    print(model.get_model_attribute(poi.ModelAttribute.TerminationStatus))

    P_value = P.map(model.get_value)

    print("Optimal active power output of the generators:")

    for i in range(N_gen):
        print(f"Generator {i}: {P_value[i]}")
