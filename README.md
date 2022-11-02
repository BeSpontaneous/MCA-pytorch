# Probing into Overfitting for Video Recognition

## Reuiqrements
- python 3.7
- pytorch 1.9.0
- torchvision 0.10.0

## Prepare datasets
Put the directory of datasets in `ROOT_DATASET` under `ops/dataset_config.py`

## Training TSM on Something-Something V1 using standard protocal
```
bash sth.sh
```

## Training TSM on Something-Something V1 with Ghost Motion and Logits Smoothing
```
bash sth_GM.sh
```