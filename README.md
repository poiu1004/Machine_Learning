# Detection of Structural Defects in Designed Protein Structures

본 저장소는 [2026-1] Machine Learning Term Project의 소스 코드와 산출물을 포함합니다.

단백질 3D 구조의 결함 여부를 이진 분류하는 머신러닝 파이프라인을 강의 범위 내 알고리즘
(Logistic Regression / Random Forest / AdaBoost / XGBoost / SVM-RBF + PCA)만으로 구현하고,
무작위 분할 대비 타겟 단위 분할에서 일반화가 얼마나 무너지는지를 정량 비교합니다.

## Project Structure

```
machine_learning/
├── data/
│   ├── raw/                          # PDB 디코이 파일 (Decoys 'R' Us / fisa, .gitignore)
│   └── processed/features.csv        # extract_features.py 산출물
├── src/
│   ├── preprocessing/
│   │   └── extract_features.py       # PDB → 6개 기하 특징 추출
│   └── models/
│       ├── baseline.py               # LR / RF / SVM 강의 범위 베이스라인 (간단 검증)
│       ├── run_experiments.py        # 메인 파이프라인 (5모델 × 2시나리오 × val 튜닝)
│       ├── failure_analysis.py       # §5.6 실패 케이스 정성 분석
│       ├── build_report.py           # term_paper.docx 생성
│       └── _archive_outside_lecture/ # 강의 범위 밖 코드 격리 (사용 안 함)
├── figures/                          # 8장의 보고서용 그림
├── results/                          # experiment_results.json, failure_analysis.json
├── requirements.txt                  # 재현용 의존성
├── term_paper.docx                   # 최종 보고서 (제출 시 PDF 변환)
└── README.md
```

## Setup

```
cd machine_learning
pip install -r requirements.txt
```

권장 환경: Python ≥ 3.10, scikit-learn ≥ 1.4, xgboost ≥ 3.0

## How to Reproduce the Report

1. **데이터 준비** — Decoys 'R' Us / fisa 세트(http://compbio.buffalo.edu/dd/download.shtml)를 다운로드 후 압축을 풀면
   다음과 같은 디렉토리 구조가 되도록 배치한다.

   ```
   data/raw/dd/multiple/fisa/
   ├── 1fc2/
   │   ├── 1fc2.pdb
   │   ├── axproa00-min.pdb   ← 디코이 PDB 파일들
   │   ├── ...
   │   └── rmsds              ← cRMSD 정보 파일
   ├── 1hdd-C/
   │   └── ...
   ├── 2cro/
   │   └── ...
   └── 4icb/
       └── ...
   ```

   다운로드한 .tar.gz를 `data/raw/`에 풀면 위 경로가 자동 생성된다.
   본 보고서는 라벨링 가능한 4개 타겟만 사용한다.

2. **특징 추출** — PDB → CSV
   ```
   cd machine_learning
   python src/preprocessing/extract_features.py
   
   ```
   
   산출물: `data/processed/features.csv` (1,070 samples × 6 features).

3. **실험 실행** — 5모델 × 2시나리오 + 튜닝 + 시각화
   ```
   cd machine_learning
   python src/models/run_experiments.py
   ```
   산출물:
   - `results/experiment_results.json`
   - `figures/pca_analysis.png`, `roc_scenario_A.png`, `roc_scenario_B.png`,
     `confusion_matrix_A.png`, `confusion_matrix_B.png`, `feature_importance_rf.png`

4. **실패 케이스 분석**
   ```
   cd machine_learning
   python src/models/failure_analysis.py
   ```
   산출물: `results/failure_analysis.json`, `figures/failure_rmsd_dist.png`, `failure_feature_shift.png`

## Random Seed and Reproducibility

모든 실험은 `random_state=42`로 고정되어 있어, 위 절차를 그대로 따르면 보고서의 모든 수치가 동일하게 재현됩니다.

## Dataset & License

- 데이터셋: Decoys 'R' Us / fisa (Samudrala & Levitt, 2000)
- 출처: http://compbio.buffalo.edu/dd/download.shtml
- 학술 출판물을 통해 공개된 벤치마크로 학술 연구 목적 사용이 관례적으로 허용되며, 본 저장소는 데이터를 재배포하지 않습니다.

## AI Tool Disclosure

본 프로젝트의 보고서 정비·코드 검토 과정에서 Anthropic Claude (Claude Opus 4.7 via Claude Code CLI)를 사용했습니다.
사용 범위와 사용자 직접 작업의 구분은  **부록 A. AI 사용 투명성**에 명시되어 있습니다.
