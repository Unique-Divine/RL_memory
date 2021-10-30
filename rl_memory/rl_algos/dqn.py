import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import distributions
import torch.optim
import numpy as np
import dataclasses
import os, sys 
try:
    import rl_memory
except:
    exec(open('__init__.py').read()) 
    import rl_memory
import rl_memory as rlm
import rl_memory.memory
import rl_memory.tools
from rl_memory.rlm_env import representations 
from rl_memory.rlm_env import environment 
from rl_memory.rl_algos import base
from rl_memory.rl_algos import trackers

# Type imports
from typing import Dict, List, Iterable, Tuple, Optional, Union
from torch import Tensor
Array = np.ndarray
Categorical = distributions.Categorical

it = representations.ImgTransforms()

@dataclasses.dataclass
class NNHyperParameters:
    """Hyperparameters for the Deep Q Network.
    
    Q: How do hyperparameters differ from the model parameters?
    A: If you have to specify a paramter manually, then it is probably a 
    hyperparameter. For example, the learning rate is a hyperparameter."""

    lr: float
    batch_size: int = 1
    num_filters: int = 16
    filter_size: int = 2
    dropout_pct: float = 0.1
    hidden_dim: int = 5

    def __post_init__(self):
        self._check_valid_batch_size()
        self._check_valid_num_filters()
        self._check_valid_dropout_pct()
        self._check_valid_hidden_dim()

    def _check_valid_batch_size(self):
        batch_size: int = self.batch_size
        assert isinstance(batch_size, int)
        assert batch_size > 0

    def _check_valid_num_filters(self):
        num_filters: int = self.num_filters
        assert isinstance(num_filters, int)
        assert num_filters > 0

    def _check_valid_hidden_dim(self):
        hidden_dim: int = self.hidden_dim
        assert isinstance(hidden_dim, int)
        assert hidden_dim > 0

    def _check_valid_dropout_pct(self):
        dropout_pct: float = self.dropout_pct
        assert isinstance(dropout_pct, (int, float))
        assert (dropout_pct >= 0) and (dropout_pct <= 1), (
            f"'dropout_pct' must be between 0 and 1, not {dropout_pct}")

# TODO
class DQN(nn.Module):
    """Neural network for vanilla policy gradient. Used in the first experiment
    
    Args:
        action_dim (int): The dimension of the action space, i.e. 
            len(action_space). 
        
    """
    def __init__(self, obs_size: torch.Size, action_dim: int, 
                 h_params: NNHyperParameters):
        super().__init__()
        self.batch_size: int = h_params.batch_size
        num_filters: int = h_params.num_filters
        filter_size: int = h_params.filter_size
        hidden_dim: int = h_params.hidden_dim

        # Model Architecture
        self.convnet_encoder: nn.Module = self._get_convnet_encoder(
            num_filters=num_filters, filter_size=filter_size)

        lin_dim: int = num_filters * (obs_size[0] - filter_size) ** 2

        self.fc_layers = nn.Sequential(
            nn.Linear(lin_dim, hidden_dim),
                nn.Dropout(h_params.dropout_pct),
                nn.ReLU(),
            nn.Linear(hidden_dim, action_dim))

        self.optimizer = torch.optim.Adam(self.parameters(), lr = h_params.lr)
        self.action_dim = action_dim

        self.memory = rl_memory.memory.Memory()

    def forward(self, x: Tensor):
        x: Tensor = x.float()
        x = self.convnet_encoder(x)
        x = self.fc_layers(x.flatten())
        return x

    def _get_convnet_encoder(self, num_filters, filter_size) -> nn.Module:
        return nn.Sequential(
            nn.Conv2d(in_channels = 3, out_channels = num_filters, 
                        kernel_size = filter_size, stride = 1),
            nn.BatchNorm2d(num_filters),
            nn.LeakyReLU(),
            nn.MaxPool2d(kernel_size=filter_size, stride=1),) 

    def get_Q_values(self, obs: rlm.Observation) -> Categorical:
        """
        Args:
            obs (Observation): grid that agent sees

        input: state (TODO adjust for when state is sequence of observations??)
        ouput: softmax(nn valuation of each action)

        Returns: 
            action_distribution (Categorical): 
        """
        obs_rgb: Tensor = it.grid_to_rgb(obs).unsqueeze(0)
        action_logits = self.forward(obs_rgb)
        return action_logits

    def update(self, memories: List[rlm.Memory], advantages):  # add entropy
        """Update with advantage policy gradient theorem."""
        # V(obs_t) = sum_t gamma^t * r_t
        # = sum_t gamma^0 r_0 + V(s_{t+1})
        # loss = MSE(V(obs_t) - (gamma*V(obs_{t+1}) + gamma^0 * r)

        advantages = torch.FloatTensor(advantages)
        log_probs = torch.cat(tensors = log_probs, dim = 0)
        assert log_probs.requires_grad
        assert not advantages.requires_grad

        loss = - torch.mean(log_probs * advantages.detach())
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

    # def update(self, log_probs, advantages):  # add entropy
    #     """Update with advantage policy gradient theorem."""
    #     advantages = torch.FloatTensor(advantages)
    #     log_probs = torch.cat(tensors = log_probs, dim = 0)
    #     assert log_probs.requires_grad
    #     assert not advantages.requires_grad
    #
    #     loss = - torch.mean(log_probs * advantages.detach())
    #     self.optimizer.zero_grad()
    #     loss.backward()
    #     self.optimizer.step()

class DQNSceneTracker(trackers.SceneTracker): # TODO
    """Container class for tracking scene-level results.

    Attributes:
        scene_rewards (List[float]): Scene rewards. Defaults to empty list.
        scene_disc_rewards (Array): Scene discounted rewards. Defaults to None.
        env_char_renders (List[Array]): Character renders of the env grid. 
            Used for visualizing how the agent moves.
    """

    def __init__(self):
        self.scene_rewards: List[float] = []
        self.scene_disc_rewards: Array = None
        self.action_idxs: List[int] = []
        self.env_char_renders: List[Array] = [] 
        super().__post_init__()

class DQNEpisodeTracker(trackers.EpisodeTracker): # TODO
    """Container class for tracking episode-level results.

    Attributes:
        episode_rewards (List[float]): List of total rewards for each episode. 
            Each element of 'episode_rewards' is the total reward for a 
            particular episode.
        episode_disc_rewards (List[float]): List of episode total returns. Each 
            element of 'episode_disc_rewards' is the total discounted reward 
            for a particular episode. Note, "returns" is another term that 
            refers to the discounted reward. 
        trajectories (List[]):
        distributions (List[Categorical]): 
    """
    
    def __init__(self):
        self.episode_rewards: List[float] = []
        self.episode_disc_rewards: List[float] = []
        self.trajectories: List = []
        self.distributions: List[Categorical] = []
        super().__post_init__()

class DQNTransferLearning(base.TransferLearningManagement): # TODO
    """Manages the transfer learning process for Vanilla Policy Gradient."""

    def __init__(self, transfer_freq: int):
        self.transfer_freq = transfer_freq

    def transfer(self, ep_idx: int, env: rlm.Env) -> rlm.Env:
        """Transfers the agent to a random environment based on the transfer 
        frequency attribute, 'freq'.
        """

        freq = self.transfer_freq
        if (ep_idx % freq == 0) and (ep_idx > 0):
            env.create_new() # Reset to a random environment (same params)
        else:
            env.reset() # Reset to the same environment
        return env

class DQNAlgo(base.RLAlgorithm): # TODO Write the DQN class and change this algo
                                 # to work with the network
    """Runs the Vanilla Policy Gradient algorithm.

    Args:
        dqn (DQN): 
        env_like (rlm.Env): 
        transfer_mgmt (Optional[base.TransferLearningManagement]): 
            Defaults to None.
        discount_factor: float = 0.99
    
    Attributes:
        episode_tracker (trackers.EpisodeTracker): 
        scene_tracker (trackers.SceneTracker):

        dqn (DQN): 
        env_like (rlm.Env): 
        transfer_mgmt (Optional[base.TransferLearningManagement]): 
            Defaults to None.
        discount_factor: float = 0.99
    """

    def __init__(
        self, 
        dqn: DQN, 
        env_like: rlm.Env, 
        transfer_mgmt: Optional[base.TransferLearningManagement] = None,
        discount_factor: float = 0.99
        ):
            
        self.dqn = dqn
        self.env_like = env_like
        self.transfer_mgmt: base.TransferLearningManagement = transfer_mgmt
        self.discount_factor = discount_factor

        self.episode_tracker = DQNEpisodeTracker()
        self.scene_tracker: DQNSceneTracker

    def run_algo(
            self, 
            num_episodes: int, 
            max_num_scenes: int,
            training: bool = True):
        """TODO: docs"""
        train_val: str = "train" if training else "val"
        if train_val == "train":
            self.dqn.train()
        else:
            self.dqn.eval()

        env: rlm.Env = self.env_like
        for episode_idx in range(num_episodes):
            env = self.on_episode_start(
                env = env, episode_idx = episode_idx)
            self.film_episode(env = env, 
                              max_num_scenes = max_num_scenes) 
            if train_val == "train":
                self.update_q_network()
            self.on_episode_end()

    def on_episode_start(
            self, 
            env: rlm.Env, 
            episode_idx: int) -> rlm.Env:
        if self.transfer_mgmt is not None:
            env = self.transfer_mgmt.transfer(
                ep_idx = episode_idx, env = env)
        else:
            env.reset()
        self.scene_tracker = DQNSceneTracker()
        return env

    def film_scene(self, env: rlm.Env) -> bool:
        """Runs a scene. A scene is one step of an episode.

        Args:
            scene_tracker (DQNSceneTracker): Stores scene-level results.

        Returns:
            done (bool): Whether or not the episode is finished.
        """
        # Observe environment
        obs: rlm.Observation = environment.Observation(env = env)
        q_vals = self.dqn(obs)
        _, best_action_idx = torch.max(q_vals, dim=1)
        
        # Perform action
        env_step: rlm.EnvStep = env.step(
            action_idx = best_action_idx, obs = obs)
        next_obs, reward, done, info = env_step
        
        # TODO update scene tracker variables 
        self.scene_tracker.action_idxs.append(action_idx)
        self.scene_tracker.scene_rewards.append(reward)
        self.scene_tracker.env_char_renders.append(env.render_as_char(env.grid))
        return done
    
    def on_scene_end(self, env: rlm.Env):
        self.scene_tracker.env_char_renders.append(
            env.render_as_char(env.grid))
    
    @staticmethod
    def agent_took_too_long(time: int, max_time: int) -> bool:
        return time == max_time
    
    def film_episode(
            self, 
            env: rlm.Env, 
            max_num_scenes: int):
        """Runs an episode.

        Args:
            env (Env): [description]
            scene_tracker (DQNSceneTracker): [description]
        """
        scene_idx = 0
        done: bool = False
        while not done:
            done: bool = self.film_scene(env = env)

            scene_idx += 1
            if done:  
                self.on_scene_end(env = env)
                break
            elif self.agent_took_too_long(
                time = scene_idx,
                max_time = max_num_scenes):
                self.scene_tracker.scene_rewards[-1] = -1  
                done = True
            else:
                continue

    def update_q_network(self):
        """Updates the weights and biases of the policy network."""
        scene_disc_rewards: Array = rl_memory.tools.discount_rewards(
            rewards = self.scene_tracker.scene_rewards, 
            discount_factor = self.discount_factor)
        self.scene_tracker.scene_disc_rewards = scene_disc_rewards
        baselines = np.zeros(scene_disc_rewards.shape)
        advantages = scene_disc_rewards - baselines

        self.dqn.update(
            action_idxs=self.scene_tracker.action_idxs, 
            advantages=advantages)

    def on_episode_end(self):
        """Stores episode results and any other actions at episode end.

        Returns:
            [type]: [description]
        """
        total_scene_reward = np.sum(self.scene_tracker.scene_rewards)
        total_scene_disc_reward = np.sum(self.scene_tracker.scene_disc_rewards)
        self.episode_tracker.episode_rewards.append(total_scene_reward)
        self.episode_tracker.episode_disc_rewards.append(
            total_scene_disc_reward)
        self.episode_tracker.trajectories.append(
            self.scene_tracker.env_char_renders)
        self.episode_tracker.distributions.append(
            self.scene_tracker.log_probs)
