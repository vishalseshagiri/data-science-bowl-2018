from functools import partial

from steps.base import Step, Dummy
from steps.preprocessing import XYSplit
from postprocessing import Resizer, Thresholder, Whatershed, NucleiLabeler, Dropper, Cutter
from loaders import MetadataImageSegmentationLoader, MetadataImageSegmentationMultitaskLoader
from models import PyTorchUNet, PyTorchUNetMultitask
from utils import squeeze_inputs


def unet(config, train_mode):
    """
    U-Net architecture
    :param config:
    :return:
    """
    if train_mode:
        save_output = True
        load_saved_output = True
        prepro = prepro_train(config)
    else:
        save_output = False
        load_saved_output = False
        prepro = prepro_inference(config)

    unet = Step(name='unet',
                transformer=PyTorchUNetMultitask(**config.unet),
                input_steps=[prepro],
                cache_dirpath=config.env.cache_dirpath,
                save_output=save_output, load_saved_output=load_saved_output)

    mask_postpro = mask_postprocessing(unet, config, save_output=save_output)

    detached = nuclei_labeler(mask_postpro, config, save_output=save_output)

    output = Step(name='output',
                  transformer=Dummy(),
                  input_steps=[detached],
                  adapter={'y_pred': ([(detached.name, 'labels')]),
                           },
                  cache_dirpath=config.env.cache_dirpath)
    return output


def unet_multitask(config, train_mode):
    """
    U-Net architecture
    :param config:
    :return:
    """

    if train_mode:
        save_output = True
        load_saved_output = True
        prepro = prepro_multitask_train(config)
    else:
        save_output = False
        load_saved_output = False
        prepro = prepro_multitask_train(config)

    unet_multitask = Step(name='unet_multitask',
                          transformer=PyTorchUNetMultitask(**config.unet),
                          input_steps=[prepro],
                          cache_dirpath=config.env.cache_dirpath,
                          save_output=save_output, load_saved_output=load_saved_output)

    mask_postpro = mask_postprocessing(unet_multitask, config, save_output=save_output)
    contour_postpro = contour_postprocessing(unet_multitask, config, save_output=save_output)
    center_postpro = center_postprocessing(unet_multitask, config, save_output=save_output)

    detached = combiner_watershed(mask_postpro, center_postpro, config, save_output=save_output)

    output = Step(name='output',
                  transformer=Dummy(),
                  input_steps=[detached],
                  adapter={'y_pred': ([(detached.name, 'labels')]),
                           },
                  cache_dirpath=config.env.cache_dirpath)
    return output


def prepro_train(config):
    xy_train = Step(name='xy_train',
                    transformer=XYSplit(**config.xy_splitter),
                    input_data=['input'],
                    adapter={'meta': ([('input', 'meta')]),
                             'train_mode': ([('input', 'train_mode')])
                             },
                    cache_dirpath=config.env.cache_dirpath)

    xy_inference = Step(name='xy_inference',
                        transformer=XYSplit(**config.xy_splitter),
                        input_data=['input'],
                        adapter={'meta': ([('input', 'meta_valid')]),
                                 'train_mode': ([('input', 'train_mode')])
                                 },
                        cache_dirpath=config.env.cache_dirpath)

    loader = Step(name='loader',
                  transformer=MetadataImageSegmentationLoader(**config.loader),
                  input_data=['input'],
                  input_steps=[xy_train, xy_inference],
                  adapter={'X': ([('xy_train', 'X')], squeeze_inputs),
                           'y': ([('xy_train', 'y')], squeeze_inputs),
                           'train_mode': ([('input', 'train_mode')]),
                           'X_valid': ([('xy_inference', 'X')], squeeze_inputs),
                           'y_valid': ([('xy_inference', 'y')], squeeze_inputs),
                           },
                  cache_dirpath=config.env.cache_dirpath)
    return loader


def prepro_inference(config):
    xy_inference = Step(name='xy_inference',
                        transformer=XYSplit(**config.xy_splitter),
                        input_data=['input'],
                        adapter={'meta': ([('input', 'meta')]),
                                 'train_mode': ([('input', 'train_mode')])
                                 },
                        cache_dirpath=config.env.cache_dirpath)

    loader = Step(name='loader',
                  transformer=MetadataImageSegmentationLoader(**config.loader),
                  input_data=['input'],
                  input_steps=[xy_inference, xy_inference],
                  adapter={'X': ([('xy_inference', 'X')], squeeze_inputs),
                           'y': ([('xy_inference', 'y')], squeeze_inputs),
                           'train_mode': ([('input', 'train_mode')]),
                           },
                  cache_dirpath=config.env.cache_dirpath)
    return loader


def prepro_multitask_train(config):
    xy_train = Step(name='xy_train',
                    transformer=XYSplit(**config.xy_splitter_multitask),
                    input_data=['input'],
                    adapter={'meta': ([('input', 'meta')]),
                             'train_mode': ([('input', 'train_mode')])
                             },
                    cache_dirpath=config.env.cache_dirpath)

    xy_inference = Step(name='xy_inference',
                        transformer=XYSplit(**config.xy_splitter_multitask),
                        input_data=['input'],
                        adapter={'meta': ([('input', 'meta_valid')]),
                                 'train_mode': ([('input', 'train_mode')])
                                 },
                        cache_dirpath=config.env.cache_dirpath)

    loader = Step(name='loader',
                  transformer=MetadataImageSegmentationMultitaskLoader(**config.loader),
                  input_data=['input'],
                  input_steps=[xy_train, xy_inference],
                  adapter={'X': ([('xy_train', 'X')], squeeze_inputs),
                           'y': ([('xy_train', 'y')]),
                           'train_mode': ([('input', 'train_mode')]),
                           'X_valid': ([('xy_inference', 'X')], squeeze_inputs),
                           'y_valid': ([('xy_inference', 'y')]),
                           },
                  cache_dirpath=config.env.cache_dirpath)

    return loader


def prepro_multitask_inference(config):
    xy_inference = Step(name='xy_inference',
                        transformer=XYSplit(**config.xy_splitter),
                        input_data=['input'],
                        adapter={'meta': ([('input', 'meta')]),
                                 'train_mode': ([('input', 'train_mode')])
                                 },
                        cache_dirpath=config.env.cache_dirpath)

    loader = Step(name='loader',
                  transformer=MetadataImageSegmentationMultitaskLoader(**config.loader),
                  input_data=['input'],
                  input_steps=[xy_inference, xy_inference],
                  adapter={'X': ([('xy_inference', 'X')], squeeze_inputs),
                           'y': ([('xy_inference', 'y')], squeeze_inputs),
                           'train_mode': ([('input', 'train_mode')]),
                           },
                  cache_dirpath=config.env.cache_dirpath)
    return loader


def mask_postprocessing(model, config, save_output=True):
    mask_resize = Step(name='mask_resize',
                       transformer=Resizer(),
                       input_data=['input'],
                       input_steps=[model],
                       adapter={'images': ([(model.name, 'mask_prediction')]),
                                'target_sizes': ([('input', 'target_sizes')]),
                                },
                       cache_dirpath=config.env.cache_dirpath,
                       save_output=save_output)

    mask_thresholding = Step(name='mask_thresholding',
                             transformer=Thresholder(**config.thresholder),
                             input_steps=[mask_resize],
                             adapter={'images': ([('mask_resize', 'resized_images')]),
                                      },
                             cache_dirpath=config.env.cache_dirpath,
                             save_output=save_output)

    return mask_thresholding


def contour_postprocessing(model, config, save_output=True):
    contour_resize = Step(name='contour_resize',
                          transformer=Resizer(),
                          input_data=['input'],
                          input_steps=[model],
                          adapter={'images': ([(model.name, 'contour_prediction')]),
                                   'target_sizes': ([('input', 'target_sizes')]),
                                   },
                          cache_dirpath=config.env.cache_dirpath,
                          save_output=save_output)

    contour_thresholding = Step(name='contour_thresholding',
                                transformer=Thresholder(**config.thresholder),
                                input_steps=[contour_resize],
                                adapter={'images': ([('contour_resize', 'resized_images')]),
                                         },
                                cache_dirpath=config.env.cache_dirpath,
                                save_output=save_output)
    return contour_thresholding


def center_postprocessing(model, config, save_output=True):
    center_resize = Step(name='center_resize',
                         transformer=Resizer(),
                         input_data=['input'],
                         input_steps=[model],
                         adapter={'images': ([(model.name, 'center_prediction')]),
                                  'target_sizes': ([('input', 'target_sizes')]),
                                  },
                         cache_dirpath=config.env.cache_dirpath,
                         save_output=save_output)

    center_thresholding = Step(name='center_thresholding',
                               transformer=Thresholder(**config.thresholder),
                               input_steps=[center_resize],
                               adapter={'images': ([('center_resize', 'resized_images')]),
                                        },
                               cache_dirpath=config.env.cache_dirpath,
                               save_output=save_output)
    return center_thresholding


def combiner_watershed(mask, center, config, save_output=True):
    watershed = Step(name='watershed',
                     transformer=Whatershed(),
                     input_steps=[mask, center],
                     adapter={'images': ([(mask.name, 'binarized_images')]),
                              'centers': ([(center.name, 'binarized_images')])
                              },
                     cache_dirpath=config.env.cache_dirpath,
                     save_output=save_output)

    drop_smaller = Step(name='drop_smaller',
                        transformer=Dropper(**config.dropper),
                        input_steps=[watershed],
                        adapter={'labels': ([('watershed', 'detached_images')]),
                                 },
                        cache_dirpath=config.env.cache_dirpath,
                        save_output=save_output)
    return drop_smaller


def nuclei_labeler(posptrocessed_mask, config, save_output=True):
    labeler = Step(name='labeler',
                   transformer=NucleiLabeler(),
                   input_steps=[posptrocessed_mask],
                   adapter={'images': ([(posptrocessed_mask.name, 'binarized_images')]),
                            },
                   cache_dirpath=config.env.cache_dirpath,
                   save_output=save_output)
    return labeler


PIPELINES = {'unet': {'train': partial(unet, train_mode=True),
                      'inference': partial(unet, train_mode=False),
                      },
             'unet_multitask': {'train': partial(unet_multitask, train_mode=True),
                                'inference': partial(unet_multitask, train_mode=False),
                                }
             }
