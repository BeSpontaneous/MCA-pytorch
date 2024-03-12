python tools/run_net.py \
  --cfg configs/sth/SLOWFAST_8x8_R50.yaml \
  DATA.PATH_TO_DATA_DIR ./data_list/sthv1 \
  DATA.PATH_PREFIX /datasets/something_v1/20bn-something-something-v1 \
  DATA.PATH_LABEL_SEPARATOR "," \
  DATA.NUM_FRAMES 32 \
  NUM_GPUS 2 \
  TRAIN.ENABLE False \
  TEST.CHECKPOINT_FILE_PATH your_model_path;