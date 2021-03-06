# This file is based on https://github.com/jhayes14/adversarial-patch
# We use square patch to test our model 

'''
The attack is learned from 27 images, each classes have 3 images.
Type 'python make_patch.py {}.pt'  to run 
{} is the name of your model want to attack.
Note that you cannot attack randomized smoothing in this file, 
please use smooth_patch.py
'''
import argparse
import os
import random
import numpy as np

import torch
import torch.nn as nn
import torch.nn.parallel
import torch.backends.cudnn as cudnn
import torch.optim as optim
import torch.utils.data
import torch.nn.functional as F
import torchvision.datasets as dset
import torchvision.transforms as transforms
from torch.autograd import Variable
from torch.utils.data.sampler import SubsetRandomSampler

from make_patch_utils import *
from new_vgg_face import VGG_16
#from save_image import save_image 
#uncomment to see images


# training is not typical training, it finds the most adversarial patchs
def train(epoch, patch, patch_shape):
    netClassifier.eval()
    success = 0
    total = 0
    recover_time = 0
    for batch_idx, (data, labels) in enumerate(train_loader):
        if labels.item()==target:
            continue
        if torch.cuda.is_available:
            data = data.cuda()
            labels = labels.cuda()
        data, labels = Variable(data), Variable(labels)
        data = data[:,[2,1,0],:,:] # rgb to bgr
        #save_image('mkpatch_oriimg',data.data)
        #uncomment to see some images

        prediction = netClassifier(data)
 
        # only computer adversarial examples on examples that are originally classified correctly        
        if prediction.data.max(1)[1][0] != labels.data[0]:
            continue
        
        total += 1
        
        # transform path
        patchcopy = np.copy(patch)
        data_shape = data.data.cpu().numpy().shape
        if patch_type == 'circle':
            patch, mask, patch_shape = circle_transform(patch, data_shape, patch_shape, image_size)
        elif patch_type == 'square':
            patch, mask  = square_transform(patch, data_shape, patch_shape, image_size)
        patch, mask = torch.FloatTensor(patch), torch.FloatTensor(mask)
        if torch.cuda.is_available:
            patch, mask = patch.cuda(), mask.cuda()
        patch, mask = Variable(patch), Variable(mask)
 
        adv_x, mask, patch = attack(data, patch, mask)
        
        adv_label = netClassifier(adv_x).data.max(1)[1][0]
        ori_label = labels.data[0]
        
        if adv_label == target:
            success += 1
      
            if plot_all == 1: 
                pass
                
        masked_patch = torch.mul(mask, patch)
        patch = masked_patch.data.cpu().numpy()
        new_patch = np.zeros(patch_shape)
        
        if submatrix(patch[0][0]).shape != new_patch[0][0].shape:
            patch = patchcopy
            continue
        
        for i in range(new_patch.shape[0]): 
            for j in range(new_patch.shape[1]): 
                new_patch[i][j] = submatrix(patch[i][j])
                
 
        patch = new_patch

        # log to file  
        #progress_bar(batch_idx, len(train_loader), "Train Patch Success: {:.3f}".format(success/total))
    print("Train Patch Accuracy is  :", 1- success/total)

    return patch

def test(epoch, patch, patch_shape):
    netClassifier.eval()
    success = 0
    total = 0
    for batch_idx, (data, labels) in enumerate(test_loader):
        if labels.item()==target:
            continue
        if torch.cuda.is_available:
            data = data.cuda()
            labels = labels.cuda()
        data, labels = Variable(data), Variable(labels)
        data = data[:,[2,1,0],:,:] # rgb to bgr

        prediction = netClassifier(data)

        # only computer adversarial examples on examples that are originally classified correctly        
        # if prediction.data.max(1)[1][0] != labels.data[0]:
        #     continue
      
        total += 1 
        
        # transform path
        data_shape = data.data.cpu().numpy().shape
        if patch_type == 'circle':
            patch, mask, patch_shape = circle_transform(patch, data_shape, patch_shape, image_size)
        elif patch_type == 'square':
            patch, mask = square_transform(patch, data_shape, patch_shape, image_size)
        patch, mask = torch.FloatTensor(patch), torch.FloatTensor(mask)
        if torch.cuda.is_available:
            patch, mask = patch.cuda(), mask.cuda()
        patch, mask = Variable(patch), Variable(mask)
 
        adv_x = torch.mul((1-mask),data) + torch.mul(mask,patch)
        adv_x = torch.clamp(adv_x, min_out, max_out)
        
        adv_label = netClassifier(adv_x).data.max(1)[1][0]
        ori_label = labels.data[0]
        
        if adv_label != ori_label:
            success += 1
       
        masked_patch = torch.mul(mask, patch)
        patch = masked_patch.data.cpu().numpy()
        new_patch = np.zeros(patch_shape)
        for i in range(new_patch.shape[0]): 
            for j in range(new_patch.shape[1]): 
                new_patch[i][j] = submatrix(patch[i][j])
 
        patch = new_patch

        # log to file  
        # progress_bar(batch_idx, len(test_loader), "Test Success: {:.3f}".format(success/total))
    print("Test Patch Accuracy is :", 1- success/total)

def attack(x, patch, mask):
    netClassifier.eval()

    x_out = F.softmax(netClassifier(x),dim=1)
    target_prob = x_out.data[0][target]

    adv_x = torch.mul((1-mask),x) + torch.mul(mask,patch)
    
    count = 0 
   
    while conf_target > target_prob:
        count += 1
        adv_x = Variable(adv_x.data, requires_grad=True)
        adv_out = F.log_softmax(netClassifier(adv_x), dim=1)
       
        adv_out_probs, adv_out_labels = adv_out.max(1)
        
        Loss = -adv_out[0][target]
        Loss.backward()
     
        adv_grad = adv_x.grad.clone()
        
        adv_x.grad.data.zero_()
        
       
        patch = patch -  5 * adv_grad/torch.max(adv_grad) 
        
        adv_x = torch.mul((1-mask),x) + torch.mul(mask,patch)
        adv_x = torch.clamp(adv_x, min_out, max_out)
 
        out = F.softmax(netClassifier(adv_x), dim=1)
        target_prob = out.data[0][target]

        if count >= opt.max_count:
            break


    return adv_x, mask, patch 


if __name__ == '__main__':
    
    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=str, help="test_model")
    parser.add_argument('--workers', type=int,  default=1, help='number of data loading workers')
    parser.add_argument('--epochs', type=int, default=20, help='number of epochs to train for')

    parser.add_argument('--target', type=int, default=0, help='The target class: 0 ')
    parser.add_argument('--conf_target', type=float, default=1, help='Stop attack on image when target classifier \
        reaches this value for target class')

    parser.add_argument('--max_count', type=int, default=100, help='max number of iterations to find adversarial example')
    parser.add_argument('--patch_type', type=str, default='square', help='patch type: circle or square')
    #parser.add_argument('--patch_size', type=float, default=0.1, help='patch size. E.g. 0.05 ~= 5% of image ')

    parser.add_argument('--train_size', type=int, default=2000, help='Number of training images')
    parser.add_argument('--test_size', type=int, default=2000, help='Number of test images')

    parser.add_argument('--image_size', type=int, default=224, help='the height / width of the input image to network')

    parser.add_argument('--plot_all', type=int, default=1, help='1 == plot all successful adversarial images')

    parser.add_argument('--outf', default='./logs', help='folder to output images and model checkpoints')
    parser.add_argument('--manualSeed', type=int, default=1338, help='manual seed')

    opt = parser.parse_args()
    print(opt)

    for patch_size in [0.05,0.1,0.15,0.2,0.25]:
        
        
        try:
            os.makedirs(opt.outf)
        except OSError:
            pass

        if opt.manualSeed is None:
            opt.manualSeed = random.randint(1, 10000)
        print("Random Seed: ", opt.manualSeed)
        random.seed(opt.manualSeed)
        np.random.seed(opt.manualSeed)
        torch.manual_seed(opt.manualSeed)
        if True:
            torch.cuda.manual_seed_all(opt.manualSeed)

        cudnn.benchmark = True


        target = opt.target
        conf_target = opt.conf_target
        max_count = opt.max_count
        patch_type = opt.patch_type
        #patch_size = opt.patch_size
        image_size = opt.image_size
        plot_all = opt.plot_all 


        print("=> creating model ")
        netClassifier_par = {'input_size': [3, 224, 224],
            'input_range': [0, 255],
            'mean': [0.367035294117647,0.41083294117647057,0.5066129411764705],
            'std': [1/255, 1/255, 1/255],
            'num_classes': 10,
            'input_space':"RGB"
            }


        netClassifier = VGG_16() 
        netClassifier.load_state_dict(torch.load('../donemodel/'+opt.model))

        if torch.cuda.is_available():
            netClassifier.cuda()
    

        print('==> Preparing data..')
        data_dir = '../Data'
        normalize = transforms.Normalize(mean=[0.367035294117647,0.41083294117647057,0.5066129411764705],
                                 std= [1/255,1/255,1/255]    )

        train_loader = torch.utils.data.DataLoader(
        dset.ImageFolder(os.path.join(data_dir, 'Train_patch'), transforms.Compose([
        transforms.Resize(round(max(netClassifier_par["input_size"])*1.050)),
        transforms.CenterCrop(max(netClassifier_par["input_size"])),
        transforms.ToTensor(),
        normalize
        ])),
        batch_size=1, shuffle=True,
        num_workers=opt.workers, pin_memory=True)
 
        test_loader = torch.utils.data.DataLoader(
        dset.ImageFolder(os.path.join(data_dir, 'val'), transforms.Compose([
        transforms.Resize(round(max(netClassifier_par["input_size"])*1.050)),
        transforms.CenterCrop(max(netClassifier_par["input_size"])),
        transforms.ToTensor(),
        normalize
        ])),
        batch_size=1, shuffle=True,
        num_workers=opt.workers, pin_memory=True)

        min_in, max_in = netClassifier_par["input_range"][0], netClassifier_par["input_range"][1]
        min_in, max_in = np.array([min_in, min_in, min_in]), np.array([max_in, max_in, max_in])
        mean, std = np.array(netClassifier_par["mean"]), np.array(netClassifier_par["std"]) 
        min_out, max_out = np.min((min_in-mean)/std), np.max((max_in-mean)/std)

        print(patch_size)
        
        if patch_type == 'circle':
            patch, patch_shape = init_patch_circle(image_size, patch_size) 
        elif patch_type == 'square':
            patch, patch_shape = init_patch_square(image_size, patch_size) 
        else:
            sys.exit("Please choose a square or circle patch")
    
        for epoch in range(1, opt.epochs + 1):
            patch = train(epoch, patch, patch_shape)
            test(epoch, patch, patch_shape)
            
            