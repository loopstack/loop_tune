'''
This file generates benchmark by leting user define loop order for matrix multiplicaiton
or convolution, and making all permutations of it enumerated with 01234...txt and saving 
it under args.out directory

Example:

python generator.py --kind=mm --size=128 --out=path-to-dir [--permute]
python generator_new.py --kind=mm --dimA=64:256:16,64:256:16 --dimB=64:256:16,64:256:16  --out=path-to-dir [--permute]
'''

import argparse
import loop_tool as lt
import numpy as np

from itertools import combinations, permutations
import os
import shutil
from pathlib import Path

from loop_tool_service.paths import LOOP_TOOL_ROOT


parser = argparse.ArgumentParser(description='Generate dataset of permutation for the constructed looptree.')

parser.add_argument(
    '--kind', choices=['mm', 'conv'], help='Kind of computation.', required=True
)
parser.add_argument(
    "--dimA",  type=str, help="Dimensions of the tensor A in csv format.", required=True
)
parser.add_argument(
    "--dimB",  type=str, help="Dimensions of the tensor B in csv format.", required=True
)
parser.add_argument(
    "--out", type=str, help="Path to folder with permutations to generate.", required=True
)
parser.add_argument(
    "--permute",  type=bool, nargs='?', const=True, default=False, help="Generate all permutations of loops."
)


def mm(A, B):
    s = lt.SymbolGenerator()
    C = A.to(s.m, s.k) * B.to(s.k, s.n)
    return C.sum(s.k)

def conv(X, W):
    s = lt.SymbolGenerator()
    X = X.pad(X.symbolic_shape[1], 1)
    return (X[s.B, s.No + s.K] * W.to(s.B, s.K)).sum(s.K)


# ********************************** mm.txt ********************************** 
def gen_mm(dimA, dimB):
    assert(dimA[1] == dimB[0])
    m, n, k = dimA[0], dimA[1], dimB[1]  # 8, 16, 128
    A = lt.Tensor(m, k).set(np.random.randn(m, k))
    B = lt.Tensor(k, n).set(np.random.randn(k, n))

    s = lt.SymbolGenerator()
    C = mm(A, B)
    return C
# ********************************** conv.txt **********************************
def gen_conv(dimA, dimB):
    n, c, h, w = lt.symbols('n c h w')
    X = lt.Tensor(*dimA).to(n, c, h, w) # 64, 8, 24, 24

    m, kh, kw = lt.symbols('m kh kw')
    W = lt.Tensor(*dimB).to(m, c, kh, kw) # 16, 8, 3, 3

    Y = lt.nn.conv(X, W, [h, w], [kh, kw])

    # nhwc output by default, we can fix that
    _, ho, wo, _ = Y.symbolic_shape
    Y = Y.transpose(n, m, ho, wo)

    print(Y.shape)
    print(Y.loop_tree)
    return Y




# ********************************** permutations.txt **********************************

def swap_loops(loop_tree, l1, l2):
    if loop_tree.loop(l1).var == loop_tree.loop(l2).var:
        for l in loop_tree.loops:
            if loop_tree.loop(l).var != loop_tree.loop(l1).var:
                return loop_tree.swap_loops(l, l1)\
                                .swap_loops(l1, l2)\
                                .swap_loops(l, l2)
    else:
        return loop_tree.swap_loops(l1, l2)


def order_loop_tree(loop_tree, order):
    cur_order = [*range(len(order))]

    for i in range(len(order)):
        for j in range(i+1, len(order)):
            if order[i] == cur_order[j]:
                loop_tree = swap_loops(loop_tree, l1=i, l2=j)
                cur_order[i], cur_order[j] = cur_order[j], cur_order[i]

    return loop_tree

def generate_permutations(loop_tree):
    loop_ids = [ x for i, x in enumerate(loop_tree.loops) if x == i ]
    loops = []
    orders = []
    for comb in combinations(loop_ids, len(loop_ids)):
        for perm in permutations(comb):
            loops.append(order_loop_tree(loop_tree, perm))
            orders.append("".join([ str(x) for x in perm]))
    return loops, orders




def parse_dim(dims_str:str):
    '''
    Input: "64:256:5,64"
\   Outputs: [[64,69,..254], [64]]
    '''
    dims = []

    for range_str in dims_str.split(','):
        range_list = [ int(x) for x in range_str.split(':') ]

        if len(range_list) == 1:
            dims.append(range_list)
        elif len(range_list) in [2,3]:
            range_list[1] += 1
            dims.append([*range(*range_list)]) # range (start, end, step)
        else:
            print('Bad format')
            exit()
        
    return dims


def gen_mm_range(dimAranges, dimBranges):
    assert (len(dimAranges) == 2)
    assert (len(dimBranges) == 2)
    tensors = []
    names = []

    for dimA0 in dimAranges[0]:
        for dimA1 in dimAranges[1]:
            for dimB1 in dimBranges[1]:
                C = gen_mm(dimA=[dimA0, dimA1], dimB=[dimA1, dimB1])
                tensors.append(C)
                names.append(f'mm{dimA0}_{dimA1}_{dimB1}')
                print(C.loop_tree)

    return tensors, names


def save_loops(loops, paths):
    for final_loop, path in zip(loops, paths):
        print(final_loop)
        try:
            final_loop.FLOPS()
            with open(path, "w") as f:
                f.write(final_loop.ir.serialize())
        except:
            print('Failed ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^')
            breakpoint()


def main():

    args = parser.parse_args()

    dimAranges = parse_dim(args.dimA)
    dimBranges = parse_dim(args.dimB)


    if args.kind == "mm":
        tensors, loop_names = gen_mm_range(dimAranges, dimBranges)
    elif args.kind == "conv":
        print('Not implemented')
        exit()
    else:
        breakpoint()
        exit()

    assert(not os.path.exists(args.out)), f"File: {args.out} already exist!"
    

    if len(tensors) == 1:
        with lt.Backend("loop_nest"):
            C = lt.ui(tensors[0], "/tmp/woo.c")
        with open(args.out, "w") as f:
            f.write(C.ir.serialize())
    else:
        os.makedirs(args.out)
        if args.permute:
            for tensor, loop_name in zip(tensors, loop_names):
                loops, orders = generate_permutations(tensor.loop_tree)
                final_paths = [ f'{args.out}/{loop_name}_{order}' for order in orders ]
                save_loops(loops, final_paths)
        else:
            final_paths = [ f'{args.out}/{loop_name}' for loop_name in loop_names ]
            final_loops = [ t.loop_tree for t in tensors ]
            save_loops(final_loops, final_paths)
            

    # Register benchmark for CompilerGym
    base_dataset_py = LOOP_TOOL_ROOT/'loop_tool_service/service_py/datasets/mm128_128_128.py'
    shutil.copyfile(base_dataset_py, base_dataset_py.parent/f'{Path(args.out).name}.py')

if __name__ == '__main__':
    main()
