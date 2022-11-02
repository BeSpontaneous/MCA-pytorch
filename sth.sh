###### standard training protocal


CUDA_VISIBLE_DEVICES=0,1 python main.py something RGB \
     --arch_file resnet_TSM \
     --arch resnet50 --num_segments 8 \
     --amp --gd 20 --lr 0.02 --lr_steps 20 40 --epochs 50 \
     --batch-size 64 -j 12 --dropout 0.5 --consensus_type=avg --eval-freq=1 \
     --temperature 1 --beta 0 --GM_prob 0 --model_path 'models' \
     --shift --shift_div=8 --shift_place=blockres --npb --round 1;