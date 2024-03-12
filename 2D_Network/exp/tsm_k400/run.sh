
#### scripts for training TSM on Kinetics400


CUDA_VISIBLE_DEVICES=0,1 python main.py kinetics_torrent RGB \
     --arch_file resnet_TSM \
     --arch resnet50 --num_segments 8 \
     --amp --gd 20 --lr 0.02 --wd 1e-4 --lr_steps 20 40 --epochs 50 \
     --batch-size 64 -j 16 --dropout 0.5 --consensus_type=avg --eval-freq=1 \
     --beta 1 --MCA_prob 0.0 --lambda_av 0.0 \
     --model_path 'models' \
     --shift --shift_div=8 --shift_place=blockres --npb --round 1;