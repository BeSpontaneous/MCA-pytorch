# Code for "TSM: Temporal Shift Module for Efficient Video Understanding"
# arXiv:1811.08383
# Ji Lin*, Chuang Gan, Song Han
# {jilin, songhan}@mit.edu, ganchuang@csail.mit.edu

import os
import time
import shutil
import torch.nn.parallel
import torch.backends.cudnn as cudnn
import torch.optim
import torch.multiprocessing as mp
import torch.utils.data
import torch.utils.data.distributed
import torch.distributed as dist
from torch.cuda.amp import autocast, GradScaler
import numpy as np
from torch.nn.utils import clip_grad_norm_
import pandas as pd
from ops.dataset import TSNDataSet
# from ops.models import TSN
import importlib
from ops.transforms import *
from opts import parser
from ops import dataset_config
from ops.utils import AverageMeter, accuracy
from ops.backbone.temporal_shift import make_temporal_pool
from torch import nn, optim
from torch.nn import functional as F
from tensorboardX import SummaryWriter


best_prec1 = 0
val_acc_top1 = []
val_acc_top5 = []
tr_acc_top1 = []
tr_acc_top5 = []
train_loss = []
valid_loss = []
epoch_log = []

def main():
    global args, best_prec1
    global val_acc_top1
    global val_acc_top5
    global tr_acc_top1
    global tr_acc_top5
    global train_loss
    global valid_loss
    global epoch_log

    args = parser.parse_args()
    
    if args.distributed:
        dist.init_process_group(backend='nccl', init_method='env://')
        torch.cuda.set_device(args.local_rank)
        device = torch.device(f'cuda:{args.local_rank}')

    num_class, args.train_list, args.val_list, args.root_path, prefix = dataset_config.return_dataset(args.dataset, args.modality)
    str_round = str(args.round)
    args.store_name = f'{args.dataset}/{args.arch_file}/{args.arch}/frame{args.num_segments}/round{str_round}/'
    if not args.distributed or (args.distributed and torch.distributed.get_rank() == 0):
        print('storing name: ' + args.store_name)
        check_rootfolders()
        

    a = str('ops.'+args.model_path)
    file = importlib.import_module(a)
    model = file.TSN(args.arch_file, num_class, args.num_segments, args.modality,
                base_model=args.arch,
                consensus_type=args.consensus_type,
                dropout=args.dropout,
                img_feature_dim=args.img_feature_dim,
                partial_bn=not args.no_partialbn,
                pretrain=args.pretrain,
                is_shift=args.shift, shift_div=args.shift_div, shift_place=args.shift_place,
                fc_lr5=not (args.tune_from and args.dataset in args.tune_from),
                temporal_pool=args.temporal_pool,
                non_local=args.non_local)

    crop_size = model.crop_size
    scale_size = model.scale_size
    input_mean = model.input_mean
    input_std = model.input_std
    policies = model.get_optim_policies()
    train_augmentation = model.get_augmentation(flip=False if 'something' in args.dataset or 'jester' in args.dataset else True)

    if args.distributed:
        model.to(device)
        model = torch.nn.parallel.DistributedDataParallel(model, device_ids=[args.local_rank],
                                                                output_device=args.local_rank, find_unused_parameters=True)
    else:
        model = torch.nn.DataParallel(model, device_ids=args.gpus).cuda()

    optimizer = torch.optim.SGD(policies,
                                args.lr,
                                momentum=args.momentum,
                                weight_decay=args.weight_decay)

    if args.resume:
        if args.temporal_pool:  # early temporal pool so that we can load the state_dict
            make_temporal_pool(model.module.base_model, args.num_segments)
        if os.path.isfile(args.resume):
            print(("=> loading checkpoint '{}'".format(args.resume)))
            checkpoint = torch.load(args.resume, map_location='cpu')
            args.start_epoch = checkpoint['epoch']
            best_prec1 = checkpoint['best_prec1']
            model.load_state_dict(checkpoint['state_dict'])
            optimizer.load_state_dict(checkpoint['optimizer'])

            val_acc_top1 = checkpoint['val_acc_top1']
            val_acc_top5 = checkpoint['val_acc_top5']
            tr_acc_top1 = checkpoint['tr_acc_top1']
            tr_acc_top5 = checkpoint['tr_acc_top5']
            train_loss = checkpoint['train_loss']
            valid_loss = checkpoint['valid_loss']
            epoch_log = checkpoint['epoch_log']
            
            print(("=> loaded checkpoint '{}' (epoch {})"
                   .format(args.evaluate, checkpoint['epoch'])))
        else:
            print(("=> no checkpoint found at '{}'".format(args.resume)))

    if args.tune_from:
        print(("=> fine-tuning from '{}'".format(args.tune_from)))
        sd = torch.load(args.tune_from)
        sd = sd['state_dict']
        model_dict = model.state_dict()
        replace_dict = []
        for k, v in sd.items():
            if k not in model_dict and k.replace('.net', '') in model_dict:
                print('=> Load after remove .net: ', k)
                replace_dict.append((k, k.replace('.net', '')))
        for k, v in model_dict.items():
            if k not in sd and k.replace('.net', '') in sd:
                print('=> Load after adding .net: ', k)
                replace_dict.append((k.replace('.net', ''), k))

        for k, k_new in replace_dict:
            sd[k_new] = sd.pop(k)
        keys1 = set(list(sd.keys()))
        keys2 = set(list(model_dict.keys()))
        set_diff = (keys1 - keys2) | (keys2 - keys1)
        print('#### Notice: keys that failed to load: {}'.format(set_diff))
        if args.dataset not in args.tune_from:  # new dataset
            print('=> New dataset, do not load fc weights')
            sd = {k: v for k, v in sd.items() if 'fc' not in k}
        if args.modality == 'Flow' and 'Flow' not in args.tune_from:
            sd = {k: v for k, v in sd.items() if 'conv1.weight' not in k}
        model_dict.update(sd)
        model.load_state_dict(model_dict)

    if args.temporal_pool and not args.resume:
        make_temporal_pool(model.module.base_model, args.num_segments)

    cudnn.benchmark = True

    # Data loading code
    if args.modality != 'RGBDiff':
        normalize = GroupNormalize(input_mean, input_std)
    else:
        normalize = IdentityTransform()

    if args.model_path == 'models_TDN':
        data_length = 5
    elif args.modality == 'RGB':
        data_length = 1
    elif args.modality in ['Flow', 'RGBDiff']:
        data_length = 5

    train_dataset = TSNDataSet(args.root_path, args.train_list, num_segments=args.num_segments,
                   new_length=data_length,
                   modality=args.modality,
                   image_tmpl=prefix,
                   transform=torchvision.transforms.Compose([
                       train_augmentation,
                       Stack(roll=(args.arch in ['BNInception', 'InceptionV3'])),
                       ToTorchFormatTensor(div=(args.arch not in ['BNInception', 'InceptionV3'])),
                       normalize,
                   ]), dense_sample=args.dense_sample)
    
    val_dataset = TSNDataSet(args.root_path, args.val_list, num_segments=args.num_segments,
                   new_length=data_length,
                   modality=args.modality,
                   image_tmpl=prefix,
                   random_shift=False,
                   transform=torchvision.transforms.Compose([
                       GroupScale(int(scale_size)),
                       GroupCenterCrop(crop_size),
                       Stack(roll=(args.arch in ['BNInception', 'InceptionV3'])),
                       ToTorchFormatTensor(div=(args.arch not in ['BNInception', 'InceptionV3'])),
                       normalize,
                   ]), dense_sample=args.dense_sample)

    if args.distributed:
        train_sampler = torch.utils.data.distributed.DistributedSampler(train_dataset)
    else:
        train_sampler = None
    
    train_loader = torch.utils.data.DataLoader(
        train_dataset, batch_size=args.batch_size, shuffle=(train_sampler is None),
        num_workers=args.workers, pin_memory=True, sampler=train_sampler,
        drop_last=True)  # prevent something not % n_GPU

    val_loader = torch.utils.data.DataLoader(
        val_dataset, batch_size=args.batch_size, shuffle=False,
        num_workers=args.workers, pin_memory=True)

    # define loss function (criterion) and optimizer
    if args.loss_type == 'nll':
        criterion = torch.nn.CrossEntropyLoss().cuda()
    else:
        raise ValueError("Unknown loss type")

    for group in policies:
        print(('group: {} has {} params, lr_mult: {}, decay_mult: {}'.format(
            group['name'], len(group['params']), group['lr_mult'], group['decay_mult'])))

    if args.evaluate:
        validate(val_loader, model, criterion, 0)
        return

    log_training = open(os.path.join(args.root_log, args.store_name, 'log.csv'), 'w')
    if not args.distributed or (args.distributed and torch.distributed.get_rank() == 0):
        with open(os.path.join(args.root_log, args.store_name, 'args.txt'), 'w') as f:
            f.write(str(args))
        tf_writer = SummaryWriter(log_dir=os.path.join(args.root_log, args.store_name))
        
    
    if args.amp:
        scaler = GradScaler()
    else:
        scaler = None

    
    for epoch in range(args.start_epoch, args.epochs):
        adjust_learning_rate(optimizer, epoch, args.lr_type, args.lr_steps)
        # train for one epoch
        tr_acc1, tr_acc5, tr_loss = train(train_loader, model, criterion, optimizer, epoch, log_training, scaler)

        # evaluate on validation set
        if (epoch + 1) % args.eval_freq == 0 or epoch == args.epochs - 1:
            val_acc1, val_acc5, val_loss = validate(val_loader, model, criterion, epoch, log_training)

            
            if not args.distributed or (args.distributed and torch.distributed.get_rank() == 0):
                # remember best prec@1 and save checkpoint
                is_best = val_acc1 > best_prec1
                best_prec1 = max(val_acc1, best_prec1)
                tf_writer.add_scalar('acc/test_top1_best', best_prec1, epoch)

                output_best = 'Best Prec@1: %.3f\n' % (best_prec1)
                print(output_best)
                log_training.write(output_best + '\n')
                log_training.flush()

                val_acc_top1.append(val_acc1)
                val_acc_top5.append(val_acc5)
                tr_acc_top1.append(tr_acc1)
                tr_acc_top5.append(tr_acc5)
                train_loss.append(tr_loss)
                valid_loss.append(val_loss)
                epoch_log.append(epoch)

                df = pd.DataFrame({'val_acc_top1': val_acc_top1, 'val_acc_top5': val_acc_top5, 
                                    'tr_acc_top1': tr_acc_top1, 'tr_acc_top5': tr_acc_top5, 
                                    'train_loss': train_loss, 'valid_loss': valid_loss,
                                    'epoch_log': epoch_log})

                log_file = os.path.join(args.root_log, args.store_name, 'log_epoch.txt')
                with open(log_file, "w") as f:
                    df.to_csv(f)

                save_checkpoint({
                    'epoch': epoch + 1,
                    'arch': args.arch,
                    'state_dict': model.state_dict(),
                    'optimizer': optimizer.state_dict(),
                    'best_prec1': best_prec1,
                    'val_acc_top1': val_acc_top1,
                    'val_acc_top5': val_acc_top5,
                    'tr_acc_top1': tr_acc_top1,
                    'tr_acc_top5': tr_acc_top5,
                    'train_loss': train_loss,
                    'valid_loss': valid_loss,
                    'epoch_log': epoch_log,
                }, is_best)
    
    
    if not args.distributed or (args.distributed and torch.distributed.get_rank() == 0):
        file1 = pd.read_csv(log_file)
        acc1 = np.array(file1['val_acc_top1'])
        loc = np.argmax(acc1)
        max_acc = acc1[loc]
        fout = open(os.path.join(args.root_log, args.store_name, 'log_epoch.txt'), mode='a', encoding='utf-8')
        fout.write("%.6f" % (max_acc))


def train(train_loader, model, criterion, optimizer, epoch, log, scaler=None):
    batch_time = AverageMeter()
    data_time = AverageMeter()
    losses = AverageMeter()
    top1 = AverageMeter()
    top5 = AverageMeter()

    if args.no_partialbn:
        model.module.partialBN(False)
    else:
        model.module.partialBN(True)

    # switch to train mode
    model.train()

    end = time.time()

    if args.amp:
        assert scaler is not None

    for i, (input, target) in enumerate(train_loader):
        # measure data loading time
        data_time.update(time.time() - end)

        target = target.cuda()
        input_var = torch.autograd.Variable(input)
        target_var = torch.autograd.Variable(target)

        optimizer.zero_grad()
        
        r = np.random.rand(1)
        if args.beta > 0 and r < args.GM_prob:
            input_var = input_var.view((-1, 3*args.num_segments) + input_var.size()[-2:])
            c = np.random.rand(1)
            batch_num = input_var.shape[0]
            lam = np.random.beta(args.beta, args.beta, batch_num)
            lam = torch.from_numpy(lam).view(-1,1,1,1).half()
            frame_idx = torch.arange(0,3*args.num_segments,1)
            if c < 0.5:
                rand_index = torch.roll(frame_idx,1,0)
            else:
                rand_index = torch.roll(frame_idx,-1,0)
            input_var = lam * input_var + (1-lam) * input_var[:, rand_index]
            input_var = input_var.view((-1, 3*args.num_segments) + input_var.size()[-2:])
        
        if args.amp:
            with autocast():
                # compute output
                output, multi_output = model(input_var)
                soft_output = output / args.temperature
                loss = criterion(soft_output, target_var)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
        else:
            output, multi_output = model(input_var)
            soft_output = output / args.temperature
            loss = criterion(soft_output, target_var)
            # compute gradient and do SGD step
            loss.backward()
            if args.clip_gradient is not None:
                total_norm = clip_grad_norm_(model.parameters(), args.clip_gradient)
            optimizer.step()
        
        # measure accuracy and record loss
        prec1, prec5 = accuracy(output.data, target, topk=(1, 5))
        losses.update(loss.item(), input.size(0))
        top1.update(prec1.item(), input.size(0))
        top5.update(prec5.item(), input.size(0))

        # measure elapsed time
        batch_time.update(time.time() - end)
        end = time.time()
        
        if not args.distributed or (args.distributed and torch.distributed.get_rank() == 0):
            if i % args.print_freq == 0:
                output = ('Epoch: [{0}][{1}/{2}], lr: {lr:.5f}\t'
                        'Time {batch_time.val:.3f} ({batch_time.avg:.3f})\t'
                        'Data {data_time.val:.3f} ({data_time.avg:.3f})\t'
                        'Loss {loss.val:.4f} ({loss.avg:.4f})\t'
                        'Prec@1 {top1.val:.3f} ({top1.avg:.3f})\t'
                        'Prec@5 {top5.val:.3f} ({top5.avg:.3f})'.format(
                    epoch, i, len(train_loader), batch_time=batch_time,
                    data_time=data_time, loss=losses, top1=top1, top5=top5, lr=optimizer.param_groups[-1]['lr'] * 0.1))  # TODO
                print(output)
                log.write(output + '\n')
                log.flush()

    return top1.avg, top5.avg, losses.avg


def validate(val_loader, model, criterion, epoch, log=None):
    batch_time = AverageMeter()
    losses = AverageMeter()
    top1 = AverageMeter()
    top5 = AverageMeter()
    mul_top1 = AverageMeter()
    mul_top5 = AverageMeter()


    # switch to evaluate mode
    model.eval()
    ece_score = 0.0
    confidence_score = 0.0

    end = time.time()
    with torch.no_grad():
        for i, (input, target) in enumerate(val_loader):
            input = input.cuda()
            target = target.cuda()
            batch_size = input.shape[0]
            mul_target = target.repeat(args.num_segments).reshape(args.num_segments,batch_size).transpose(0,1).reshape(-1)

            # compute output
            output, multi_output = model(input)
            soft_output = output / args.temperature
            loss = criterion(soft_output, target)
            
            softmaxes = F.softmax(soft_output, dim=1)
            confidences, predictions = torch.max(softmaxes, 1)
            confidence_score += torch.mean(confidences)
            
            ece_loss = _ECELoss(n_bins=15)
            score = ece_loss(soft_output.cpu(), target.cpu())
            ece_score += score

            # measure accuracy and record loss
            prec1, prec5 = accuracy(output.data, target, topk=(1, 5))
            mul_prec1, mul_prec5 = accuracy(multi_output.data, mul_target, topk=(1, 5))

            losses.update(loss.item(), input.size(0))
            top1.update(prec1.item(), input.size(0))
            top5.update(prec5.item(), input.size(0))
            mul_top1.update(mul_prec1.item(), input.size(0))
            mul_top5.update(mul_prec5.item(), input.size(0))
 
            # measure elapsed time
            batch_time.update(time.time() - end)
            end = time.time()

            
            if not args.distributed or (args.distributed and torch.distributed.get_rank() == 0):
                if i % args.print_freq == 0:
                        output = ('Test: [{0}/{1}]\t'
                                'Time {batch_time.val:.3f} ({batch_time.avg:.3f})\t'
                                'Loss {loss.val:.4f} ({loss.avg:.4f})\t'
                                'mul_Prec@1 {mul_top1.val:.3f} ({mul_top1.avg:.3f})\t'
                                'mul_Prec@5 {mul_top5.val:.3f} ({mul_top5.avg:.3f})\t'
                                'Prec@1 {top1.val:.3f} ({top1.avg:.3f})\t'
                                'Prec@5 {top5.val:.3f} ({top5.avg:.3f})'.format(
                            i, len(val_loader), batch_time=batch_time, loss=losses,
                            mul_top1=mul_top1, mul_top5=mul_top5, top1=top1, top5=top5))
                        print(output)
                        if log is not None:
                            log.write(output + '\n')
                            log.flush()
            
    print(ece_score/len(val_loader))
    print(confidence_score/len(val_loader))

    if not args.distributed or (args.distributed and torch.distributed.get_rank() == 0):
        output = ('Testing Results: Prec@1 {top1.avg:.3f} Prec@5 {top5.avg:.3f} frame_Prec@1 {mul_top1.avg:.3f} frame_Prec@5 {mul_top5.avg:.3f} Loss {loss.avg:.5f}'
                .format(top1=top1, top5=top5, mul_top1=mul_top1, mul_top5=mul_top5, loss=losses))
        print(output)
        if log is not None:
            log.write(output + '\n')
            log.flush()

    return top1.avg, top5.avg, losses.avg


def save_checkpoint(state, is_best):
    filename = '%s/%s/ckpt.pth.tar' % (args.ckpt_log, args.store_name)
    torch.save(state, filename)
    if is_best:
        shutil.copyfile(filename, filename.replace('pth.tar', 'best.pth.tar'))


def adjust_learning_rate(optimizer, epoch, lr_type, lr_steps):
    """Sets the learning rate to the initial LR decayed by 10 every 30 epochs"""
    if lr_type == 'step':
        decay = 0.1 ** (sum(epoch >= np.array(lr_steps)))
        lr = args.lr * decay
        decay = args.weight_decay
    elif lr_type == 'cos':
        import math
        lr = 0.5 * args.lr * (1 + math.cos(math.pi * epoch / args.epochs))
        decay = args.weight_decay
    else:
        raise NotImplementedError
    for param_group in optimizer.param_groups:
        param_group['lr'] = lr * param_group['lr_mult']
        param_group['weight_decay'] = decay * param_group['decay_mult']


def check_rootfolders():
    """Create log and model folder"""
    folders_util = [args.root_log, os.path.join(args.root_log, args.store_name)]
    for folder in folders_util:
        if not os.path.exists(folder):
            print('creating folder ' + folder)
            os.makedirs(folder)
    ckpt_folders_util = [args.ckpt_log, os.path.join(args.ckpt_log, args.store_name)]
    for folder in ckpt_folders_util:
        if not os.path.exists(folder):
            print('creating folder ' + folder)
            os.makedirs(folder)


class _ECELoss(nn.Module):
    """
    Calculates the Expected Calibration Error of a model.
    (This isn't necessary for temperature scaling, just a cool metric).
    The input to this loss is the logits of a model, NOT the softmax scores.
    This divides the confidence outputs into equally-sized interval bins.
    In each bin, we compute the confidence gap:
    bin_gap = | avg_confidence_in_bin - accuracy_in_bin |
    We then return a weighted average of the gaps, based on the number
    of samples in each bin
    See: Naeini, Mahdi Pakdaman, Gregory F. Cooper, and Milos Hauskrecht.
    "Obtaining Well Calibrated Probabilities Using Bayesian Binning." AAAI.
    2015.
    """
    def __init__(self, n_bins=15):
        """
        n_bins (int): number of confidence interval bins
        """
        super(_ECELoss, self).__init__()
        bin_boundaries = torch.linspace(0, 1, n_bins + 1)
        self.bin_lowers = bin_boundaries[:-1]
        self.bin_uppers = bin_boundaries[1:]

    def forward(self, logits, labels):
        softmaxes = F.softmax(logits, dim=1)
        confidences, predictions = torch.max(softmaxes, 1)
        accuracies = predictions.eq(labels)

        ece = torch.zeros(1, device=logits.device)
        for bin_lower, bin_upper in zip(self.bin_lowers, self.bin_uppers):
            # Calculated |confidence - accuracy| in each bin
            in_bin = confidences.gt(bin_lower.item()) * confidences.le(bin_upper.item())
            prop_in_bin = in_bin.float().mean()
            if prop_in_bin.item() > 0:
                accuracy_in_bin = accuracies[in_bin].float().mean()
                avg_confidence_in_bin = confidences[in_bin].mean()
                ece += torch.abs(avg_confidence_in_bin - accuracy_in_bin) * prop_in_bin
        return ece



if __name__ == '__main__':
    main()