# 2D Network for Video Recognition

## Requirements
- python 3.7
- torch 1.11.0
- torchvision 0.12.0

## Implementation Details
1. We uniformly sample 8 frames during training and inference. 
2. We use 1-clip 1-crop evaluation for 2D network with the resolution of 224x224.
3. `lambda_av` denotes the coefficient $\lambda_{av}$ in the loss function and we set it to be $1, 0.65, 0.4$ on Something-Something V1, V2, Kinetics400 datasets, respectively
4. We train 2D network TSM with 2 NVIDIA Tesla V100 (32GB) cards and the model is pretrained on ImageNet.

## Training
1. Specify the directory of datasets with `ROOT_DATASET` in `ops/dataset_config.py`.
2. Simply run the training scripts in [exp](exp) as followed:

   ```
   bash exp/tsm_sthv1/run.sh  ## baseline training
   bash exp/tsm_sthv1/run_MCA.sh   ## MCA training
   ```

## Inference
1. Specify the directory of datasets with `ROOT_DATASET` in `ops/dataset_config.py`.
2. Please download pretrained models from [Google Drive](https://drive.google.com/drive/folders/1anktOMWzoWiZA3rvb9Tax4Y26ULoGU16?usp=sharing).
3. Specify the directory of the pretrained model with `resume` in `test.sh`.
4. Run the inference scripts in [exp](exp) as followed:

   ```
   bash exp/tsm_sthv1/test.sh
   ```