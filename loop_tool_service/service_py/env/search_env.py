import random
import networkx as nx
from loop_tool_service.service_py.utils import timed_fn
import time
import matplotlib as mpl
import numpy as np

def getColor(gflops): #fade (linear interpolate) from color c1 (at mix=0) to c2 (mix=1)
    # colors = ['#9495ff', '#94adff', '#94b6ff', '#94dcff', '#b3f3fe', '#febfb3', '#f8a293', '#fd8570', '#f6573a']
    # return colors[int(len(colors) * (gflops/120))]

    c1='#fdf5df'
    c2='#e06666' #red
    # c1 = "#8A5AC2"
    # c2 = "#3575D5"

    norm = gflops / 120
    c1=np.array(mpl.colors.to_rgb(c1))
    c2=np.array(mpl.colors.to_rgb(c2))
    return mpl.colors.to_hex((1-norm) * c1 + norm * c2)




class SearchGraph:
    def __init__(self, evaluator):
        self.evaluator = evaluator
        self.graph = nx.MultiDiGraph()
        self.best_key = None
        self.action_max_time = {} # Time of last action added for each member of sequence

    def expand(self, agent, num_steps, search_width, eval_mode, start_time, ranking=True, timeout=10000000): # pair(actions, reward)
        assert (num_steps >= 0), "BeamSearcherDFS num steps must be >= 0"
        agent_copy = agent.copy()
        agent_key = hash(agent_copy.dump())

        self.expand_core(
            agent=agent_copy, 
            search_depth=num_steps, 
            search_width=search_width,
            eval_mode=eval_mode,
            start_time=start_time,
            ranking=ranking,
            timeout=timeout,
        )

        if self.graph.nodes[agent_key]['gflops'] <= self.graph.nodes[self.best_key]['gflops']:
            return self.graph.nodes[self.best_key]['actions'][len(agent.actions):]
        else:
            return []
        


    def expand_core(self, agent, search_depth, search_width, eval_mode, start_time, ranking, timeout):
        node_time = time.time() - start_time
        node_key = hash(agent.dump())
        real_flops = self.evaluator.eval_gflops(agent, 'loop_nest')

        self.action_max_time[len(agent.actions)] = node_time

        if node_key not in self.graph or self.graph.nodes[node_key] == {} or len(agent.actions) < len(self.graph.nodes[node_key]['actions']):
            self.graph.add_node(
                node_key,
                label=f'GFLOPS = {real_flops:9.4f}\n T = {node_time:9.4f} s\n{agent.actions}', #+ agent.dump().replace(':', ';'),
                gflops=real_flops,
                actions=agent.actions,
                time=node_time,
                fillcolor=getColor(real_flops),
                style='filled',
            )

            if self.best_key == None or real_flops > self.graph.nodes[self.best_key]['gflops']: 
                self.best_key = node_key
            


        if search_depth == 0 or node_time > timeout:
            return


        if ranking:
            chosen_actions = [ x[0] for x in self.evaluator.get_actions_q_sorted(agent, eval_mode=eval_mode)[:search_width] ]
        else:
            chosen_actions = agent.get_available_actions()
            random.shuffle(chosen_actions)
            chosen_actions = chosen_actions[:search_width]

        for action in chosen_actions:
            agent_copy = agent.copy()
            agent_copy.apply_action(action)
            self.graph.add_edge(hash(agent.dump()), hash(agent_copy.dump()), key=action, label=action, color='black')
            self.expand_core(agent_copy, search_depth - 1, search_width, eval_mode, start_time, ranking, timeout)



    def get_best_path_data(self):
        #nx.shortest_path(graph, agent_key, self.best_key)
        cur_node = self.best_key
        actions, rewards= [], []

        for action in reversed(self.graph.nodes[self.best_key]['actions']):
            parent_node = {data['label']: k for k, v, data in self.graph.in_edges(cur_node, data=True)}[action]
            actions.insert(0, action)
            rewards.insert(0, self.graph.nodes[cur_node]['gflops'])
            self.graph.nodes[cur_node]['color'] = 'red'
            self.graph.nodes[cur_node]['penwidth'] = 5
            self.graph[parent_node][cur_node][action]['color'] = 'red'
            self.graph[parent_node][cur_node][action]['penwidth'] = '8'
            cur_node = parent_node

        self.graph.nodes[cur_node]['color'] = 'red'
        self.graph.nodes[cur_node]['penwidth'] = 5

        actions.insert(0, '')
        rewards.insert(0, self.graph.nodes[cur_node]['gflops'])
        
        action_max_time_final = [self.action_max_time[0]]
        for i in range(1, len(self.action_max_time)):
            action_max_time_final.append(max(action_max_time_final[-1], self.action_max_time[i]))

        return [actions, rewards, action_max_time_final]




class GreedySearcher:
    def __init__(self, evaluator):
        self.evaluator = evaluator

    def search(self, agent, num_steps, lookahead, search_width, eval_mode, timeout, debug=False): # actions, reward
        search_graph = SearchGraph(evaluator=self.evaluator)
        agent_copy = agent.copy()
        agent_copy.clear_actions()
        start_time = time.time()

        for i in range(num_steps):
            best_actions = search_graph.expand(
                agent=agent_copy, 
                num_steps=lookahead, 
                search_width=search_width, 
                eval_mode=eval_mode, 
                start_time=start_time, 
                ranking=False, 
                timeout=timeout/num_steps,
            )

            if len(best_actions) == 0 or time.time() - start_time > timeout: 
                break
            elif i + len(best_actions) >= num_steps:
                for action in best_actions[:num_steps - i]:
                    agent_copy.apply_action(action)                    
                break
            else:
                action = best_actions[0]
                agent_copy.apply_action(action)
        
        search_table = search_graph.get_best_path_data()

        if debug:
            print(nx.nx_pydot.to_pydot(search_graph.graph))

        return search_table


class BeamSearcherDFS:
    """ Uses policy beam search first to find n best candidates. For each candidate apply another beam search.
    """
    def __init__(self, evaluator):
        self.evaluator = evaluator

    def search(self, agent, num_steps, search_width, eval_mode, ranking, timeout, debug=False):
        search_graph = SearchGraph(evaluator=self.evaluator)
        agent_copy = agent.copy()
        agent_copy.clear_actions()

        start_time = time.time()
        search_graph.expand(
            agent=agent, 
            num_steps=num_steps, 
            search_width=search_width, 
            eval_mode=eval_mode, 
            start_time=start_time, 
            ranking=ranking, 
            timeout=timeout
        )

        search_table = search_graph.get_best_path_data()

        if debug:        
            print(nx.nx_pydot.to_pydot(search_graph.graph))

        return search_table



class BeamSearcherBFS:
    """ Uses policy beam search first to find n best candidates. For each candidate apply another beam search.
    """
    def __init__(self, evaluator):
        self.evaluator = evaluator

    def search(self, agent, num_steps, search_width, eval_mode, ranking, timeout, debug=False):
        search_graph = SearchGraph(evaluator=self.evaluator)
        agent_copy = agent.copy()
        agent_copy.clear_actions()
        frontier_agents = [agent_copy]
        start_time = time.time()

        for _ in range(num_steps):
            for agent_frontier in frontier_agents:
                search_graph.expand(
                    agent=agent_frontier, 
                    num_steps=1, 
                    search_width=search_width, 
                    eval_mode=eval_mode, 
                    start_time=start_time, 
                    ranking=ranking, 
                    timeout=timeout/num_steps
                )
            
            frontier_nodes = [node for node in search_graph.graph.nodes if search_graph.graph.out_degree(node) == 0]
            for x in frontier_nodes: 
                agent_copy = agent.copy()
                for action in search_graph.graph.nodes[x]['actions']:
                    agent_copy.apply_action(action)
                
                frontier_agents.append(agent_copy)
                
                    
        search_table = search_graph.get_best_path_data()


        if debug:
            print(nx.nx_pydot.to_pydot(search_graph.graph))

        return search_table



class RandomSearcher:
    """ 
        Explore random sequences from the space.
    """
    def __init__(self, evaluator):
        self.evaluator = evaluator

    def search(self, agent, num_steps, eval_mode, timeout, debug=False):
        search_graph = SearchGraph(evaluator=self.evaluator)
        agent_copy = agent.copy()
        agent_copy.clear_actions()
        start_time = time.time()
    
        while time.time() - start_time < timeout:
            search_graph.expand(
                agent=agent, 
                num_steps=num_steps, 
                search_width=1, 
                eval_mode=eval_mode, 
                start_time=start_time, 
                ranking=False, 
                timeout=timeout
            )

        search_table = search_graph.get_best_path_data()

        if debug:        
            print(nx.nx_pydot.to_pydot(search_graph.graph))

        return search_table

