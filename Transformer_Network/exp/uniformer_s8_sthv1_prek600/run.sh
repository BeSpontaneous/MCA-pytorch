work_path=$(dirname $0)
PYTHONPATH=$PYTHONPATH:./slowfast \
python tools/run_net.py \
  --cfg $work_path/config.yaml \
  DATA.PATH_TO_DATA_DIR ./data_list/sthv1 \
  DATA.PATH_PREFIX /datasets/something_v1/20bn-something-something-v1 \
  DATA.PATH_LABEL_SEPARATOR "," \
  TRAIN.EVAL_PERIOD 5 \
  TRAIN.CHECKPOINT_PERIOD 1 \
  TRAIN.BATCH_SIZE 32 \
  TRAIN.MCA_PROB 0.0 \
  TRAIN.BETA 1.0 \
  TRAIN.LAMBDA_AV 0.0 \
  NUM_GPUS 4 \
  UNIFORMER.DROP_DEPTH_RATE 0.2 \
  SOLVER.MAX_EPOCH 60 \
  SOLVER.BASE_LR 2e-4 \
  SOLVER.WARMUP_EPOCHS 5.0 \
  DATA.TEST_CROP_SIZE 224 \
  TEST.NUM_ENSEMBLE_VIEWS 1 \
  TEST.NUM_SPATIAL_CROPS 1 \
  OUTPUT_DIR $work_path
