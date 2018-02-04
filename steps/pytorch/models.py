from functools import partial
import shutil

import numpy as np
import torch
import torch.nn as nn
from torch.autograd import Variable
from torch.nn import init
from tqdm import tqdm

from steps.base import BaseTransformer
from .utils import get_logger, save_model

logger = get_logger()


class Model(BaseTransformer):
    def __init__(self, architecture_config, training_config, callbacks_config):
        super().__init__()
        self.architecture_config = architecture_config
        self.training_config = training_config
        self.callbacks_config = callbacks_config

        self.model = None
        self.optimizer = None
        self.loss_function = None
        self.output_names = None
        self.callbacks = None

    def _initialize_model_weights(self):
        logger.info('initializing model weights...')
        weights_init_config = self.architecture_config['weights_init']

        if weights_init_config['function'] == 'normal':
            weights_init_func = partial(init_weights_normal, **weights_init_config['params'])
        elif weights_init_config['function'] == 'xavier':
            weights_init_func = init_weights_xavier
        else:
            raise NotImplementedError

        self.model.apply(weights_init_func)

    def fit(self, datagen, validation_datagen=None):
        self._initialize_model_weights()

        if torch.cuda.is_available():
            self.model = self.model.cuda()
        else:
            self.model = self.model

        self.callbacks.set_params(self, validation_datagen=validation_datagen)
        self.callbacks.on_train_begin()

        batch_gen, steps = datagen
        for epoch_id in range(self.training_config['epochs']):
            self.callbacks.on_epoch_begin()
            for batch_id, data in enumerate(batch_gen):
                self.callbacks.on_batch_begin()
                metrics = self._fit_loop(data)
                self.callbacks.on_batch_end(metrics=metrics)
                if batch_id == steps:
                    break
            self.callbacks.on_epoch_end()
            if self.callbacks.training_break():
                break
        self.callbacks.on_train_end()
        return self

    def _fit_loop(self, data):
        X, target_tensor = data

        if torch.cuda.is_available():
            X, target_var = Variable(X).cuda(), Variable(target_tensor).cuda()
        else:
            X, target_var = Variable(X), Variable(target_tensor)

        self.optimizer.zero_grad()
        output = self.model(X)
        partial_batch_losses = {}
        for (name, loss_function) in self.loss_function:
            partial_batch_losses['batch_{}'.format(name)] = loss_function(output, target_var)
        batch_loss = sum(partial_batch_losses.values())
        partial_batch_losses['batch_loss'] = batch_loss
        batch_loss.backward()
        self.optimizer.step()

        return partial_batch_losses

    def _transform(self, datagen, validation_datagen=None):
        self.model.eval()
        batch_gen, steps = datagen
        outputs = []
        for batch_id, data in enumerate(batch_gen):
            if len(data) == 2:
                X, targets = data
            else:
                X = data

            if torch.cuda.is_available():
                X = Variable(X).cuda()
            else:
                X = Variable(X)
            output = self.model(X)
            outputs.append(output.data.cpu().numpy())

            if batch_id == steps:
                break

        outputs = np.vstack(outputs)
        return outputs

    def transform(self, datagen, validation_datagen=None):
        predictions = self._transform(datagen, validation_datagen)
        return NotImplementedError

    def load(self, filepath):
        self.model.eval()

        if torch.cuda.is_available():
            self.model.cpu()
            self.model.load_state_dict(torch.load(filepath))
            self.model.cuda()
        else:
            self.model.load_state_dict(torch.load(filepath, map_location=lambda storage, loc: storage))
        return self

    def save(self, filepath):
        checkpoint_callback = self.callbacks_config.get('model_checkpoint')
        if checkpoint_callback:
            checkpoint_filepath = checkpoint_callback['filepath']
            shutil.copyfile(checkpoint_filepath, filepath)

        else:
            save_model(self.model, filepath)


class ModelMultitask(Model):
    def _fit_loop(self, data):
        X = data[0]
        targets_tensors = data[1:]

        if torch.cuda.is_available():
            X = Variable(X).cuda()
            targets_var = []
            for target_tensor in targets_tensors:
                targets_var.append(Variable(target_tensor).cuda())
        else:
            X = Variable(X)
            targets_var = []
            for target_tensor in targets_tensors:
                targets_var.append(Variable(target_tensor))

        self.optimizer.zero_grad()
        outputs = self.model(X)
        partial_batch_losses = {}
        for (name, loss_function), output, target in zip(self.loss_function, outputs, targets_var):
            partial_batch_losses['batch_{}'.format(name)] = loss_function(output, target)
        batch_loss = sum(partial_batch_losses.values())
        partial_batch_losses['batch_loss'] = batch_loss
        batch_loss.backward()
        self.optimizer.step()

        return partial_batch_losses

    def _transform(self, datagen, validation_datagen=None):
        self.model.eval()
        batch_gen, steps = datagen
        outputs = {}
        for batch_id, data in enumerate(batch_gen):
            if len(data) == len(self.output_names) + 1:
                X = data[0]
                targets_tensors = data[1:]
            else:
                X = data

            if torch.cuda.is_available():
                X = Variable(X).cuda()
            else:
                X = Variable(X)

            outputs_batch = self.model(X)
            if len(outputs_batch) == len(self.output_names):
                for name, output in zip(self.output_names, outputs_batch):
                    outputs.setdefault(name, []).append(output.data.cpu().numpy())
            else:
                outputs.setdefault(self.output_names[0], []).append(outputs_batch.data.cpu().numpy())

            if batch_id == steps:
                break

        outputs = {'{}_prediction'.format(name): np.vstack(outputs_) for name, outputs_ in outputs.items()}
        return outputs


class PyTorchBasic(nn.Module):
    def _flatten_features(self, in_size, features):
        f = features(Variable(torch.ones(1, *in_size)))
        return int(np.prod(f.size()[1:]))

    def forward(self, x):
        features = self.features(x)
        flat_features = features.view(-1, self.flat_features)
        out = self.classifier(flat_features)
        return out

    def forward_target(self, x):
        return self.forward(x)


def init_weights_normal(model, mean, std_conv2d, std_linear):
    if type(model) == nn.Conv2d:
        model.weight.data.normal_(mean=mean, std=std_conv2d)
    if type(model) == nn.Linear:
        model.weight.data.normal_(mean=mean, std=std_linear)


def init_weights_xavier(model):
    if isinstance(model, nn.Conv2d):
        init.xavier_normal(model.weight)
        init.constant(model.bias, 0)
