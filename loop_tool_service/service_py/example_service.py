#! /usr/bin/env python3
#
#  Copyright (c) Facebook, Inc. and its affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
"""An example CompilerGym service in python."""

import logging
import os
import pdb
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pkg_resources import working_set

from copy import deepcopy

from env import loop_tool_env
import json

import compiler_gym.third_party.llvm as llvm
from compiler_gym import site_data_path
from compiler_gym.service import CompilationSession
from compiler_gym.service.proto import (
    ActionSpace,
    Benchmark,
    Space,
    NamedDiscreteSpace,
    Event,
    ObservationSpace,
    DoubleRange,
    SendSessionParameterReply,
    ByteSequenceSpace,
    BytesSequenceSpace,
    Int64Range,
    CommandlineSpace,
    StringSpace,
    DoubleSequenceSpace,
    Int64SequenceSpace,
    DoubleBox,
    DoubleTensor,
    FloatTensor,
    FloatBox,
    FloatRange,
    BooleanTensor,
    BooleanBox,
    BooleanRange,
)
from compiler_gym.service.runtime import create_and_run_compiler_gym_service

import utils
import signal
import sys
import numpy as np

import loop_tool as lt


class LoopToolCompilationSession(CompilationSession):
    """Represents an instance of an interactive compilation session."""

    max_loops: int = lt.LoopTreeAgent.max_loops()
    num_loop_features: int = lt.LoopTreeAgent.num_loop_features()
    compiler_version: str = "1.0.0"

    # keep it simple for now: 1 variable, 1 nest
    action_spaces = [
        ActionSpace(
            name="loop_tool",
            space=Space(
                # potentially define new splits
                named_discrete=NamedDiscreteSpace(
                    name=[
                        # "dummy",
                        "up", 
                        "down", 
                        "swap_up", 
                        "swap_down", 
                        # "split_2", 
                        # "split_4", 
                        # "split_8", 
                        # "split_16", 
                        # "split_32", 
                        # "split_64", 
                        # "split_128", 
                        # "split_256", 
                        # "split_512", 
                        # "split_1024", 
                        # "merge", 
                        # "unroll", 
                        # "vectorize", 
                        # "increase_reuse",
                        # "decrease_reuse"

                        # "copy_input_0", #TODO: Copy input should be parametric action 0,1,...n is id of variable
                        # "copy_input_1",
                        # "copy_input_2",
                        # "copy_input_3",
                        ],
                ),
            ),
        ),
    ]

    observation_spaces = [
        ObservationSpace(
            name="runtime_tensor",
            space=Space(
                double_box=DoubleBox(
                    low = DoubleTensor(shape = [1], value=[0]),
                    high = DoubleTensor(shape = [1], value=[float("inf")]),
                )
            ),
            deterministic=False,
            platform_dependent=True,
            default_observation=Event(
                double_value=0,
            ),
        ),
        ObservationSpace(
            name="runtime",
            space=Space(double_value=DoubleRange()),
            deterministic=False,
            platform_dependent=True,
            default_observation=Event(
                double_value=0,
            ),
        ),
        ObservationSpace(
            name="flops",
            space=Space(double_value=DoubleRange()),
            deterministic=False,
            platform_dependent=True,
            default_observation=Event(
                double_value=0,
            ),
        ),
        ObservationSpace(
            name="flops_loop_nest",
            space=Space(double_value=DoubleRange()),
            deterministic=False,
            platform_dependent=True,
            default_observation=Event(
                double_value=0,
            ),
        ),
        ObservationSpace(
            name="flops_loop_nest_tensor",
            space=Space(
                double_box=DoubleBox(
                    low = DoubleTensor(shape = [1], value=[0]),
                    high = DoubleTensor(shape = [1], value=[float("inf")]),
                )
            ),
            deterministic=False,
            platform_dependent=True,
            default_observation=Event(
                double_value=0,
            ),
        ),
        ObservationSpace(
            name="ir",
            space=Space(
                string_value=StringSpace(length_range=Int64Range(min=0)),
            ),
            deterministic=True,
            platform_dependent=False,
            default_observation=Event(
                string_value="",
            ),
        ),
        ObservationSpace(
            name="loop_tree",
            space=Space(
                string_value=StringSpace(length_range=Int64Range(min=0)),
            ),
            deterministic=True,
            platform_dependent=False,
            default_observation=Event(
                string_value="",
            ),
        ),        
        ObservationSpace(
            name="ir_tree_networkx",
            space=Space(
                byte_sequence=ByteSequenceSpace(length_range=Int64Range(min=0)),
            ),
        ),
        ObservationSpace(
            name="ir_graph_networkx",
            space=Space(
                byte_sequence=ByteSequenceSpace(length_range=Int64Range(min=0)),
            ),
        ),        
        ObservationSpace( # Note: Be CAREFUL with dimensions, they need to be exactly the same like in perf.py
            name="loops_tensor",
            space=Space(
                float_box=FloatBox(
                    low = FloatTensor(shape = [1, max_loops * num_loop_features], value=[0] * max_loops * num_loop_features),
                    high = FloatTensor(shape = [1, max_loops * num_loop_features], value=([1] + [1] * max_loops + [int(1e6), int(1e6), 1, 1, 1] + [1] * 32) * max_loops),
                )
            ),
            deterministic=False,
            platform_dependent=True,
            default_observation=Event(
                float_tensor=FloatTensor(shape = [1, max_loops * num_loop_features], value=[0] * max_loops * num_loop_features),
            ),
        ),
        ObservationSpace( # Note: Be CAREFUL with dimensions, they need to be exactly the same like in perf.py
            name="stride_tensor",
            space=Space(
                float_box=FloatBox(
                    low = FloatTensor(shape = [1, 32], value=[0] * 32),
                    high = FloatTensor(shape = [1, 32], value=[int(1e6)] * 32),
                )
            ),
            deterministic=False,
            platform_dependent=True,
            default_observation=Event(
                float_tensor=FloatTensor(shape = [1, 32], value=[0] * 32),
            ),
        ),
        ObservationSpace( # Note: Ret pos of the cursor (simple check if network learns)
            name="5_prev_actions_tensor",
            space=Space(
                float_box=FloatBox(
                    low = FloatTensor(shape = [1, 5 * 4], value=[0] * 5 * 4),
                    high = FloatTensor(shape = [1, 5 * 4], value=[1] * 5 * 4),
                )
            ),
            deterministic=False,
            platform_dependent=True,
            default_observation=Event(
                float_tensor=FloatTensor(shape = [1, 5 * 4], value=[0] * 5 * 4),
            ),
        ),
    ]
    

    def __init__(
        self,
        working_directory: Path,
        action_space: ActionSpace,
        benchmark: Benchmark,
        save_state: bool = True,
        env: loop_tool_env.Environment = None
    ):
        self.working_dir = working_directory
        self.action_space = action_space
        self.benchmark = benchmark
        self.timeout_sec = 3000

        super().__init__(working_directory, action_space, benchmark)
        logging.info(f"Started a compilation session for {benchmark.uri}")
        self._action_space = action_space

        os.chdir(str(working_directory))
        # logging.critical(f"\n\nWorking_dir = {str(working_directory)}\n")
        # breakpoint()

        self.save_state = save_state if save_state != None else True
        
        if env == None:
            self.env = loop_tool_env.Environment(
                                working_directory=working_directory,
                                action_space=action_space,
                                observation_spaces=self.observation_spaces,
                                benchmark=benchmark,
                                timeout_sec=self.timeout_sec,
            )
        else:
            self.env = env

        self.cur_iter = 0
        self.prev_observation = {}

    def handle_session_parameter(self, key: str, value: str) -> Optional[str]:
        if key == "save_state":
            self.save_state = False if value == "0" else True
            return "Succeeded"
        
        elif key == "save_restore":
            if value == '0': # save
                self.env.agent_saved = self.env.agent.copy() #deepcopy()
            else: # restore
                self.env.agent = self.env.agent_saved.copy() #deepcopy(self.env.agent_saved)
            return "Succeeded"
        
        elif key == "load_cost_model":
            self.env.load_cost_model(value)
            return ""
        
        elif key == "load_policy_model":
            self.env.load_policy_model(value)
            return ""

        elif key == "greedy_search": # value = "walk_count, step_count, search_depth, search_width"
            walk_count, step_count, search_depth, search_width = value.split(',')

            # import cProfile
            # import cProfile, pstats
            # profiler = cProfile.Profile()
            # breakpoint()
            # profiler.enable()
            # breakpoint()
            best_actions_reward = self.env.greedy_search(
                int(walk_count), 
                int(step_count),
                search_depth=int(search_depth), 
                search_width=int(search_width),
            )

            # profiler.disable()
        
            # stats = pstats.Stats(profiler).sort_stats('cumtime')
            # stats.print_stats()
            # breakpoint()

            return json.dumps(best_actions_reward)

        elif key == "policy_search": # value = "search_depth, num_strategies"
            search_depth, num_strategies = value.split(',')

            best_actions_reward = self.env.policy_search(   # Must initialize policy, (and cost) model first
                search_depth=int(search_depth),
                num_strategies=int(num_strategies)
            )

            return json.dumps(best_actions_reward)
        

        elif key == "available_actions":
            return json.dumps(self.env.get_available_actions())
        
        elif key == "undo_action":
            self.env.agent.undo_action()
            return ""
        
        elif key == "print_looptree":
            print(self.env.agent.actions)
            print(self.env.agent)
            return ""
        else:
            logging.critical("handle_session_parameter Unsuported key:", key)
            return ""


    def apply_action(self, action: Event) -> Tuple[bool, Optional[ActionSpace], bool]:
        new_action_space = False
        end_of_session = False
        action_had_effect = False

        num_choices = len(self.action_spaces[0].space.named_discrete.name)
        choice_index = action.int64_value
        if choice_index < 0 or choice_index >= num_choices:
            raise ValueError("Out-of-range")

        # Compile benchmark with given optimization
        action = self._action_space.space.named_discrete.name[choice_index]
        if action not in self.env.get_available_actions():
            logging.info(f"ACTION_NOT_AVAILABLE (action = {action})")
            logging.info(f"Actions = {self.env.get_available_actions()}")
            return (end_of_session, new_action_space, not action_had_effect)

        logging.info(
            f"Applying action {choice_index}, equivalent command-line arguments: '{action}'"
        )

        action_had_effect = self.env.apply_action(action=action, save_state=self.save_state)          
        
        logging.info(f'Action = {action}')
        logging.info(self.env.agent)
        
        logging.info(f"\naction_had_effect ({action}) = {action_had_effect}\n")

        if self.env.lt_changed:
            self.prev_observation = {} # Clear cache if action had an effect

        # new_action_space = ActionSpace(
        #     name="available_actions",
        #     space=Space(
        #         # potentially define new splits
        #         named_discrete=NamedDiscreteSpace(
        #             name=self.env.get_available_actions()
        #         ),
        #     ),
        # )

        self.cur_iter += 1
        logging.info(f">>> AGENT ITERATION = {self.cur_iter}, actions = {self.env.actions}")
        return (end_of_session, new_action_space, not action_had_effect)




    def get_observation(self, observation_space: ObservationSpace) -> Event:
        logging.info(f"Computing observation from space {observation_space.name}")  

        if observation_space.name in self.prev_observation:            
            logging.info(f"get_observation: Fast return prev_observation {self.prev_observation}")
            return self.prev_observation[observation_space.name]

        if observation_space.name == "runtime":
            observation = self.env.get_runtime()
        elif observation_space.name == "flops":
            observation = self.env.get_flops()
        elif observation_space.name == "flops_loop_nest":
            observation = self.env.get_flops_loop_nest()
        elif observation_space.name == "flops_loop_nest_tensor":
            return self.env.get_flops_loop_nest_tensor()
        elif observation_space.name == "ir":
            observation = self.env.get_ir()
            return observation
        elif observation_space.name == "ir_tree_networkx":
            observation = self.env.get_ir_tree_networkx() 
            return observation
        elif observation_space.name == "ir_graph_networkx":
            observation = self.env.get_ir_graph_networkx() 
            return observation
        elif observation_space.name == "loops_tensor":
            observation = self.env.get_loops_tensor() 
            return observation
        elif observation_space.name == "stride_tensor":
            observation = self.env.get_stride_tensor() 
            return observation           
        elif observation_space.name == "loop_tree":
            observation = self.env.get_loop_tree()    
            return observation
        elif observation_space.name == "5_prev_actions_tensor":
            return self.env.get_prev_actions()
        else:
            raise KeyError(observation_space.name)

        self.prev_observation[observation_space.name] = observation

        logging.info(f"get_observation: Slow return prev_observation {self.prev_observation}")
        return self.prev_observation[observation_space.name]


    def fork(self) -> CompilationSession:
        # There is a problem with forking.
        # from copy import deepcopy
        # new_fork = deepcopy(self)
        # new_fork = super().fork()
        # print(new_fork)

        return LoopToolCompilationSession(
            working_directory=self.working_dir,
            action_space=self.action_space,
            benchmark=self.benchmark,
            save_state=self.save_state,
            env=self.env,
        )


if __name__ == "__main__":
    create_and_run_compiler_gym_service(LoopToolCompilationSession)

