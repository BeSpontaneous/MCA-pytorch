# Transformer Network for Video Recognition

## Requirements
Please follow the installation instructions in [INSTALL.md](INSTALL.md).

## Implementation Details
1. We uniformly sample 8 frames during training and inference. 
2. We use 1-clip 1-crop evaluation for Transformer network with the resolution of 224x224.
3. `TRAIN.LAMBDA_AV` denotes the coefficient $\lambda_{AV}$ in the loss function and we set it to be 1.
4. We train Transformer network Uniformer-S with 4 NVIDIA Tesla V100 (32GB) cards and the model is pretrained on Kinetics600 before training on Something-Something V1.

## Training
1. Specify the directory of datasets with `DATA.PATH_PREFIX` in `exp/uniformer_s8_sthv1_prek600_MCA/run.sh`.
2. Download the pretrained model on Kinetics600 from the [original repo](https://drive.google.com/file/d/1-dqzjm5RZVspWHQLRD4S1vo4_6jyVltb/view?usp=sharing) and specify the path with `PRETRAIN_NAME` in `exp/uniformer_s8_sthv1_prek600_MCA/config.yaml`.
3. Simply run the training scripts in [exp](exp) as followed:

   ```
   bash exp/uniformer_s8_sthv1_prek600/run.sh  ## baseline training
   bash exp/uniformer_s8_sthv1_prek600_MCA/run.sh   ## MCA training
   ```

## Inference
1. Specify the directory of datasets with `DATA.PATH_PREFIX` in `exp/uniformer_s8_sthv1_prek600_MCA/test.sh`.
2. Please download pretrained models from [Google Drive](https://drive.google.com/drive/folders/1anktOMWzoWiZA3rvb9Tax4Y26ULoGU16?usp=sharing).
3. Specify the directory of the pretrained model with `TEST.CHECKPOINT_FILE_PATH` in `test.sh`.
4. Run the inference scripts in [exp](exp) as followed:

   ```
   bash exp/uniformer_s8_sthv1_prek600_MCA/test.sh
   ```