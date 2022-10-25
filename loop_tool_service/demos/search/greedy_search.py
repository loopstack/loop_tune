# Copyright (c) Facebook, Inc. and its affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
"""Perform a random walk of the action space of a CompilerGym environment.

Example usage:

    # Run a random walk on cBench example program using perf runtime reward.
    $ python demo_random_walk.py --walk_count=2 --step_count=4 --data_set=benchmark://poj104-small-v0 --reward=perf_tensor --observation=perf_tensor

"""
from importlib.metadata import entry_points
import random
import pdb
import uuid
import os
import sys
import json

from loop_tool_service.paths import LOOP_TOOL_ROOT


from compiler_gym.util.registration import register
from tqdm import tqdm
import argparse


parser = argparse.ArgumentParser(description="LoopTool Optimizer")

parser.add_argument("--data_set", type=str, nargs='?', default="benchmark://mm128_128_128-v0", help="Data set.")
parser.add_argument("--cost_model", type=str, nargs='?', const=f"{str(LOOP_TOOL_ROOT)}/loop_tool_service/models/weights/model_cost.pth", default='', help="Path to the RLlib optimized network.")
parser.add_argument("--policy_model", type=str, nargs='?', const=f"{str(LOOP_TOOL_ROOT)}/loop_tool_service/models/weights/policy_model.pt", default='', help="Path to the RLlib optimized network.")
parser.add_argument("--search", type=str, nargs='?', default='greedy', help="Kind of search to run.")


parser.add_argument("--bench_count", type=int, nargs='?', default=2, help="The number of benchmarks.")
parser.add_argument("--search_depth", type=int, nargs='?', default=1, help="How deep you go in search before you decide.")
parser.add_argument("--search_width", type=int, nargs='?', default=1000, help="The number action you expand every level of the search.")
parser.add_argument("--walk_count", type=int, nargs='?', default=1, help="The number of walks.")
parser.add_argument("--step_count", type=int, nargs='?', default=6, help="The number of steps.")

args = parser.parse_args()


import loop_tool_service
from loop_tool_service.service_py.rewards import flops_loop_nest_reward
from loop_tool_service.service_py.datasets import loop_tool_test_dataset, loop_tool_dataset





import logging
def main():
    """Main entry point."""
    # assert len(argv) == 1, f"Unrecognized flags: {argv[1:]}"
    # This two lines try to suppress logging to stdout.
    logging.basicConfig(level=logging.CRITICAL, force=True)
    # logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, force=True)

    with loop_tool_service.make_env("loop_tool_env-v0", datasets=['mm128_128_128']) as env:

        data_set = env.datasets[args.data_set]
        i = 0
        for bench in tqdm(data_set, total=min(len(data_set), args.bench_count)):
            if i == args.bench_count: break
            print(bench)
            env.reset()
            env.send_param("print_looptree", "")

            if args.policy_model != '':
                env.send_param('load_policy_model', args.policy_model)

            if args.cost_model != '':
                env.send_param('load_cost_model', args.cost_model)


            if args.search == 'greedy':
                best_actions_reward = json.loads(env.send_param("greedy_search", 
                    f'--steps={args.step_count} --lookahead={args.search_depth} --width={args.search_width} --eval=loop_nest')
                )

            else:
                print('Search not supported')
                break

            print(best_actions_reward)
            breakpoint()
            i += 1


        
if __name__ == "__main__":
    main()
