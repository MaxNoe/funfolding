import numpy as np
from scipy import stats
import copy

from IPython import embed


def f_entropy(y, sample_weight):
    sum_w = np.sum(sample_weight)
    p = np.bincount(y, sample_weight) / float(sum_w)
    ep = stats.entropy(p)
    if ep == -float('inf'):
        return 0.0
    return ep

def select_data(y, sample_weight, split_mask):
    y_r = y[split_mask]
    y_l = y[~split_mask]
    w_r = sample_weight[split_mask]
    w_l = sample_weight[~split_mask]
    return y_r, w_r, y_l, w_l



class Node(object):
    def __init__(self,
                 base_tree,
                 path,
                 entropy,
                 sum_w,
                 split_mask,
                 split_mask_data,
                 direction):
        self.path = path
        self.base_tree = base_tree
        self.split_mask = split_mask
        self.split_mask_data = split_mask_data
        self.direction = direction
        self.random_state = base_tree.random_state
        if len(path) == 0:
            self.parent = -1
        else:
            self.parent = path[-1]
        self.depth = len(path)

        self.new_split_mask = None
        self.must_be_terminal = True
        self.feature = -2
        self.threshold = -2
        self.information_gain = np.inf

        self.info_cache = self.InfoCache()

        self.entropy = entropy
        self.sum_w = sum_w

    class InfoCache:
        def __init__(self,
                     entropy_l=None,
                     entropy_r=None,
                     sum_w_l=None,
                     sum_w_r=None,
                     path=None):
            entropy_l = entropy_l
            entropy_r = entropy_r
            sum_w_l = sum_w_l
            sum_w_r = sum_w_r

    def calc_entropies(self, y, sample_weight, split_mask):
        y_r, w_r, y_l, w_l = select_data(y, sample_weight, split_mask)
        ent_r = f_entropy(y_r, w_r)
        ent_l = f_entropy(y_l, w_l)
        return ent_r, np.sum(w_r), ent_l, np.sum(w_l)

    def optimize(self):
        print('OPTIMIZI')
        full_feature_list = np.arange(self.base_tree.n_features)
        if self.base_tree.max_features != -1:
            feature_list = np.sort(self.random_state.choice(
                full_feature_list,
                self.base_tree.max_features,
                replace=False))
        else:
            feature_list = full_feature_list
        X = self.base_tree.X[self.split_mask]
        y = self.base_tree.y[self.split_mask]
        sample_weight = self.base_tree.sample_weight[self.split_mask]
        total_weight = self.base_tree.total_weight
        #  Check if a valid split is possible
        if self.split_mask_data is None:
            frac_weight = np.sum(sample_weight) / total_weight
            n_samples_term = len(self.split_mask)
            X_data = None
        else:
            w_data = self.base_tree.sample_weight_data[self.split_mask_data]
            frac_weight = np.sum(w_data) / total_weight
            n_samples_term = len(self.split_mask_data)
            X_data = self.base_tree.X_data[self.split_mask_data]

        min_weight_fraction_leaf = self.base_tree.min_weight_fraction_leaf
        min_samples_split = self.base_tree.min_samples_split

        if n_samples_term < min_samples_split:
            return False
        if frac_weight < min_weight_fraction_leaf:
            return False

        sample_weight = self.base_tree.sample_weight[self.split_mask]
        min_weight_fraction_leaf = self.base_tree.min_weight_fraction_leaf
        min_samples_split = self.base_tree.min_samples_split
        total_weight = self.base_tree.total_weight
        if sum(self.split_mask) < min_samples_split:
            print('Too less events')
            return False
        if sum(sample_weight) / total_weight < min_weight_fraction_leaf:
            print('Weight fraction to low')
            return False
        #  Find and test all valid splits
        for feature_i in feature_list:
            X_i = X[:, feature_i]
            possible_splits = np.unique(X_i)
            resoluton_i = self.base_tree.resolution.get(feature_i, None)
            if resoluton_i is not None:
                feature_idx = np.where(self.base_tree.feature == feature_i)[0]
                cuts_done = [self.base_tree.threshold[idx]
                             for idx in feature_idx]
                for cut_i in cuts_done:
                    mask = np.absolute(cut_i - possible_splits) >= resoluton_i
                    possible_splits = possible_splits[mask]
            for split_i in possible_splits:
                new_split_mask = X_i < split_i
                entropy_r, w_r, entropy_l, w_l = self.calc_entropies(
                    y,
                    sample_weight,
                    new_split_mask)
                information_gain = entropy_r * w_r / self.sum_w
                information_gain += entropy_l * w_l / self.sum_w
                information_gain /= 2.
                information_gain -= self.entropy
                min_gain = self.base_tree.min_information_gain_split
                min_samples_leaf = self.base_tree.min_samples_leaf
                if X_data is not None:
                    new_split_mask_data = X_data < split_i
                    n_samples_l = np.sum(~new_split_mask_data)
                    n_samples_r = np.sum(new_split_mask_data)
                else:
                    new_split_mask_data = None
                    n_samples_l = np.sum(~new_split_mask)
                    n_samples_r = np.sum(new_split_mask)
                try:
                    #  Check if the splits is valid
                    assert information_gain > min_gain
                    assert n_samples_l > min_samples_leaf
                    assert n_samples_r > min_samples_leaf
                except AssertionError:
                    pass
                else:
                    if np.isinf(self.information_gain):
                        self.information_gain = 0.
                        self.must_be_terminal = False
                    if information_gain > self.information_gain:
                        self.feature = feature_i
                        self.threshold = split_i
                        self.information_gain = information_gain

                        self.info_cache.entropy_l = entropy_l
                        self.info_cache.entropy_r = entropy_r
                        self.info_cache.sum_w_l = w_l
                        self.info_cache.sum_w_r = w_r

                        f_mask = copy.copy(self.split_mask)
                        f_mask[self.split_mask] = new_split_mask
                        if self.split_mask_data is not None:
                            mask_data = self.split_mask_data
                            f_mask_data = copy.copy(mask_data)
                            f_mask_data[mask_data] = new_split_mask_data
                        else:
                            f_mask_data = None
                        self.new_split_mask = f_mask
                        self.new_split_mask_data = f_mask_data
        return True

        def __lt__(self, partner):
            if isinstance(partner, Node):
                return self.information_gain < partner.information_gain
            elif isinstance(partner, float):
                return self.information_gain < partner
            else:
                try:
                    partner = float(partner)
                except ValueError:
                    raise TypeError('Only floats and Nodes can be compared!')
                else:
                    return self.information_gain < partner


    def register(self, terminal=False):
        idx = len(self.base_tree.depth)
        if self.direction.lower() == 'l':
            self.base_tree.children_left[self.parent] = idx
        if self.direction.lower() == 'r':
            self.base_tree.children_right[self.parent] = idx
        self.base_tree.children_right.append(None)
        self.base_tree.children_left.append(None)
        self.base_tree.feature.append(self.feature)
        self.base_tree.threshold.append(self.threshold)
        self.base_tree.information_gain.append(self.information_gain)
        self.base_tree.parent.append(self.parent)
        self.base_tree.depth.append(self.depth)
        self.base_tree.entropy.append(self.entropy)
        self.base_tree.sum_w.append(self.sum_w)
        if terminal or self.must_be_terminal:
            self.base_tree.children_right[-1] = -1
            self.base_tree.children_left[-1] = -1
            return None, None
        else:
            new_path = copy.copy(self.path)
            new_path.append(idx)
            if terminal:
                l_node = None
                r_node = None
            else:
                l_node = Node(base_tree=self.base_tree,
                              path=new_path,
                              entropy=self.info_cache.entropy_l,
                              sum_w=self.info_cache.sum_w_l,
                              split_mask=~self.new_split_mask,
                              split_mask_data=self.new_split_mask_data,
                              direction='l')
                r_node = Node(base_tree=self.base_tree,
                              path=new_path,
                              entropy=self.info_cache.entropy_r,
                              sum_w=self.info_cache.sum_w_r,
                              split_mask=self.new_split_mask,
                              split_mask_data=self.new_split_mask_data,
                              direction='r')
            return l_node, r_node


class DiscretizationTree(object):
    def __init__(self,
                 max_depth=None,
                 max_features=None,
                 max_leaf_nodes=None,
                 min_information_gain_split=1e-07,
                 min_samples_leaf=1,
                 min_samples_split=2,
                 min_weight_fraction_leaf=0.0,
                 random_state=None):
        # Random State
        if not isinstance(random_state, np.random.RandomState):
            self.random_state = np.random.RandomState(random_state)
        else:
            self.random_state = random_state
        #  Options
        if max_depth is None:
            self.max_depth = np.inf
        else:
            self.max_depth = max_depth
        self.max_features = max_features
        if max_leaf_nodes is None or max_leaf_nodes == -1:
            self.max_leaf_nodes = np.inf
        else:
            self.max_leaf_nodes = max_leaf_nodes
        self.min_information_gain_split = min_information_gain_split
        self.min_samples_leaf = min_samples_leaf
        self.min_samples_split = min_samples_split
        self.min_weight_fraction_leaf = min_weight_fraction_leaf
        #  Arrays
        self.children_left = []
        self.children_right = []
        self.feature = []
        self.information_gain = []
        self.entropy = []
        self.sum_w = []
        self.threshold = []
        self.value = []
        self.weighted_n_node_samples = []
        self.parent = []
        self.depth = []
        #  Quantities
        self.node_count = -1
        self.max_depth = -1
        self.n_classes = -1
        self.n_features = -1
        self.n_outputs = -1
        self.max_depth = -1
        # Train Options
        self.resolution = {}
        self.X = None
        self.y = None
        self.sample_weight = None
        self.X_data = None
        self.sample_weight_data = None
        self.total_weight = None

    def decision_path(self, X):
        path = []
        node_pointer = 0
        while True:
            path.append(node_pointer)
            x_i = X[self.feature[node_pointer]]
            if x_i > self.threshold[node_pointer]:
                node_pointer = self.children_left[node_pointer]
            else:
                node_pointer = self.children_right[node_pointer]
            if node_pointer == -1:
                break
        return path

    def train(self,
              X,
              y,
              sample_weight=None,
              resolution=None,
              X_data=None,
              sample_weight_data=None):
        if isinstance(resolution, dict):
            self.resolution = resolution
        self.n_features = X.shape[1]
        if isinstance(self.max_features, int):
            self.max_features = min(self.max_features, self.n_features)
        else:
            self.max_features = self.n_features
        self.X = X
        self.y = y
        if sample_weight is None:
            sample_weight = np.ones_like(y, dtype=float)
        self.sample_weight = sample_weight
        init_split_mask = np.ones_like(self.y, dtype=bool)
        if X_data is not None:
            self.X_data = X_data
            if sample_weight_data is None:
                sample_weight_data = np.ones_like(y, dtype=float)
            self.sample_weight_data = sample_weight_data
            self.total_weight = np.sum(self.sample_weight_data)
            init_split_mask_data = np.ones_like(self.X_data, dtype=bool)
        else:
            self.total_weight = np.sum(self.sample_weight)
            init_split_mask_data = None
        current_depth = 0
        keep_building = True
        while keep_building:
            node_list = []
            # generate temporary nodes
            if current_depth == 0:
                root = Node(base_tree=self,
                            path=[],
                            entropy=f_entropy(y, sample_weight),
                            sum_w=np.sum(sample_weight),
                            split_mask=init_split_mask,
                            split_mask_data=init_split_mask_data,
                            direction='n')
                node_list.append(root)
            for node in node_list:
                if current_depth != self.max_depth:
                    node.optimize()

            sorted_nodes = sorted(node_list)
            print(sorted_nodes)
            # embed()
            node_list = []
            for i, optimized_node in enumerate(sorted_nodes):
                unregistered_nodes = len(sorted_nodes[i:]) + len(node_list)
                n_potential_leaves = self.max_leaf_nodes - self.n_outputs
                if n_potential_leaves <= unregistered_nodes + 2:
                    #  Check is node has to be a leaf to not violate
                    #  n_max_outpus in future
                    terminal = True
                elif current_depth == self.max_depth:
                    terminal = True
                else:
                    terminal = False
                r_node, l_node = optimized_node.register(terminal=terminal)
                if r_node is not None and l_node is not None:
                    node_list.append(r_node)
                    node_list.append(l_node)
                    self.node_count += 2
            current_depth += 1
            if len(node_list) == 0:
                keep_building = False

class TreeBinning(object):
    def __init__(self,
                 max_depth=None,
                 max_features=None,
                 max_leaf_nodes=None,
                 min_information_gain_split=1e-07,
                 min_samples_leaf=1,
                 min_samples_split=2,
                 min_weight_fraction_leaf=0.0,
                 random_state=None):
        self.tree = DiscretizationTree(
            max_depth=max_depth,
            max_features=max_features,
            max_leaf_nodes=max_leaf_nodes,
            min_information_gain_split=min_information_gain_split,
            min_samples_leaf=min_samples_leaf,
            min_samples_split=min_samples_split,
            min_weight_fraction_leaf=min_weight_fraction_leaf,
            random_state=random_state)
        self.leaf_idx_mapping = None
        self.n_bins = None

    def digitize(self, X):
        decision_pathes = self.decision_path(X)
        leafyfied = [l[-1] for l in decision_pathes]
        digitized = np.array([self.leaf_idx_mapping[val_i]
                              for val_i in leafyfied])
        return np.array(digitized)

    def decision_path(self, X):
        n_events = X.shape[0]
        decision_pathes = []
        for i in range(n_events):
            decision_pathes.append(self.tree.decision_path(X[i, :]))
        return decision_pathes

    def fit(self,
            X,
            y,
            sample_weight=None,
            resolution=None,
            X_data=None,
            sample_weight_data=None):
        self.tree.train(X,
                        y,
                        sample_weight=sample_weight,
                        resolution=resolution,
                        X_data=X_data,
                        sample_weight_data=sample_weight_data)
        self.leaf_idx_mapping = {}
        is_leaf = np.where(self.tree.feature == -2)[0]
        counter = 0
        for is_leaf_i in is_leaf:
            self.leaf_idx_mapping[is_leaf_i] = counter
            counter += 1
        self.n_bins = len(self.leaf_idx_mapping)
        return self
