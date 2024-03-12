# 3D Network for Video Recognition

## Requirements
Please follow the installation instructions in [INSTALL.md](INSTALL.md).

## Implementation Details
1. We uniformly sample 32 frames during training and inference. 
2. We use 1-clip 1-crop evaluation for 3D network with the resolution of 256x256 following the original implementation.
3. `TRAIN.LAMBDA_AV` denotes the coefficient $\lambda$ in the loss function and we set it to be 0.75.
4. We train 3D network SlowFast with 4 NVIDIA Tesla V100 (32GB) cards and the model is pretrained on Kinetics400 before training on Something-Something V1.

## Training
1. Specify the directory of datasets with `DATA.PATH_PREFIX` in `exp/slowfast_sthv1/run.sh`.
2. Specify the directory of output with `OUTPUT_DIR` in `run.sh`.
3. Download the pretrained model on Kinetics400 from the [original repo](https://dl.fbaipublicfiles.com/pyslowfast/model_zoo/kinetics400/SLOWFAST_8x8_R50.pkl) and specify the path with `CHECKPOINT_FILE_PATH` in `configs/sth/SLOWFAST_8x8_R50_FFN.yaml`.
4. Simply run the training scripts in [exp](exp) as followed:

   ```
   bash exp/slowfast_sthv1/run.sh  ## baseline training
   bash exp/slowfast_sthv1/run_MCA.sh   ## MCA training
   ```

## Inference
1. Specify the directory of datasets with `DATA.PATH_PREFIX` in `exp/slowfast_sthv1/test.sh`.
2. Please download pretrained models from [Google Drive](https://drive.google.com/drive/folders/1anktOMWzoWiZA3rvb9Tax4Y26ULoGU16?usp=sharing).
3. Specify the directory of the pretrained model with `TEST.CHECKPOINT_FILE_PATH` in `test.sh`.
4. Run the inference scripts in [exp](exp) as followed:

   ```
   bash exp/slowfast_sthv1/test.sh
   ```