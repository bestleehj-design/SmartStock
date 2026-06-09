#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI模型训练脚本
根据AI训练数据建议实现模型训练
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime
import pickle
import json
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

# 机器学习相关
try:
    from sklearn.model_selection import TimeSeriesSplit, GridSearchCV
    from sklearn.preprocessing import StandardScaler, MinMaxScaler, LabelEncoder
    from sklearn.metrics import (
        mean_absolute_error, mean_squared_error, r2_score,
        accuracy_score, precision_score, recall_score, f1_score,
        roc_auc_score, classification_report, confusion_matrix
    )
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("⚠️ scikit-learn未安装")

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    print("⚠️ XGBoost未安装")

try:
    import lightgbm as lgb
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False
    print("⚠️ LightGBM未安装")

try:
    import matplotlib.pyplot as plt
    import seaborn as sns
    PLOTTING_AVAILABLE = True
except ImportError:
    PLOTTING_AVAILABLE = False
    print("⚠️ matplotlib/seaborn未安装，无法绘图")

# 设置中文字体
if PLOTTING_AVAILABLE:
    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False


class StockModelTrainer:
    """股票模型训练器"""
    
    def __init__(self, data_file: str, output_dir: str = 'models'):
        """
        初始化训练器
        
        Args:
            data_file: 训练数据CSV文件路径
            output_dir: 模型输出目录
        """
        self.data_file = data_file
        self.output_dir = output_dir
        self.models = {}
        self.scalers = {}
        self.feature_names = []
        self.label_names = []
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
    def load_data(self) -> pd.DataFrame:
        """加载训练数据"""
        print("📥 加载训练数据...")
        df = pd.read_csv(self.data_file, encoding='utf-8-sig')
        print(f"✅ 加载 {len(df)} 条数据")
        return df
    
    def preprocess_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        数据预处理
        
        Args:
            df: 原始数据
            
        Returns:
            预处理后的数据
        """
        print("🔄 数据预处理...")
        
        # 转换日期格式
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], format='%Y%m%d', errors='coerce')
        
        # 处理缺失值
        # 数值特征：用0填充
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        df[numeric_cols] = df[numeric_cols].fillna(0)
        
        # 分类特征：用空字符串填充
        categorical_cols = ['industry', 'name', 'trend_type']
        for col in categorical_cols:
            if col in df.columns:
                df[col] = df[col].fillna('')
        
        # 处理无穷大值
        df = df.replace([np.inf, -np.inf], 0)
        
        print(f"✅ 预处理完成，数据形状: {df.shape}")
        return df
    
    def prepare_features_and_labels(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, pd.Series]]:
        """
        准备特征和标签
        
        Args:
            df: 预处理后的数据
            
        Returns:
            (特征DataFrame, 标签字典)
        """
        print("🔧 准备特征和标签...")
        
        # 排除的列（非特征列）
        exclude_cols = ['code', 'date', 'name', 'industry']
        
        # 标签列（以return_、is_、max_drawdown_开头）
        label_cols = [col for col in df.columns 
                     if col.startswith('return_') or 
                        col.startswith('is_') or 
                        col.startswith('max_drawdown_')]
        
        # 特征列（除了排除列和标签列）
        feature_cols = [col for col in df.columns 
                       if col not in exclude_cols and col not in label_cols]
        
        # 提取特征
        X = df[feature_cols].copy()
        self.feature_names = feature_cols
        
        # 提取标签
        labels = {}
        for col in label_cols:
            if col in df.columns:
                labels[col] = df[col].copy()
        
        self.label_names = list(labels.keys())
        
        print(f"✅ 特征数量: {len(feature_cols)}")
        print(f"✅ 标签数量: {len(labels)}")
        print(f"   特征列: {feature_cols[:10]}..." if len(feature_cols) > 10 else f"   特征列: {feature_cols}")
        print(f"   标签列: {list(labels.keys())}")
        
        return X, labels
    
    def split_data_by_time(self, df: pd.DataFrame, 
                          train_end: str = '2023-12-31',
                          val_end: str = '2024-12-31') -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        按时间划分数据（时间序列数据不能随机划分）
        
        Args:
            df: 数据
            train_end: 训练集结束日期
            val_end: 验证集结束日期
            
        Returns:
            (训练集, 验证集, 测试集)
        """
        print("📊 按时间划分数据...")
        
        if 'date' not in df.columns:
            raise ValueError("数据中必须包含'date'列")
        
        train_end = pd.to_datetime(train_end)
        val_end = pd.to_datetime(val_end)
        
        train_df = df[df['date'] <= train_end].copy()
        val_df = df[(df['date'] > train_end) & (df['date'] <= val_end)].copy()
        test_df = df[df['date'] > val_end].copy()
        
        print(f"✅ 训练集: {len(train_df)} 条 ({train_df['date'].min()} 到 {train_df['date'].max()})")
        print(f"✅ 验证集: {len(val_df)} 条 ({val_df['date'].min()} 到 {val_df['date'].max()})")
        print(f"✅ 测试集: {len(test_df)} 条 ({test_df['date'].min()} 到 {test_df['date'].max()})")
        
        return train_df, val_df, test_df
    
    def scale_features(self, X_train: pd.DataFrame, 
                      X_val: pd.DataFrame = None,
                      X_test: pd.DataFrame = None,
                      method: str = 'standard') -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        特征标准化
        
        Args:
            X_train: 训练集特征
            X_val: 验证集特征
            X_test: 测试集特征
            method: 标准化方法 ('standard' 或 'minmax')
            
        Returns:
            标准化后的特征
        """
        print(f"📏 特征标准化 (方法: {method})...")
        
        if method == 'standard':
            scaler = StandardScaler()
        elif method == 'minmax':
            scaler = MinMaxScaler()
        else:
            raise ValueError(f"未知的标准化方法: {method}")
        
        # 只对数值特征进行标准化
        numeric_cols = X_train.select_dtypes(include=[np.number]).columns.tolist()
        
        # 训练scaler
        X_train_scaled = X_train.copy()
        X_train_scaled[numeric_cols] = scaler.fit_transform(X_train[numeric_cols])
        
        # 保存scaler
        self.scalers[method] = scaler
        
        # 转换验证集和测试集
        if X_val is not None:
            X_val_scaled = X_val.copy()
            X_val_scaled[numeric_cols] = scaler.transform(X_val[numeric_cols])
        else:
            X_val_scaled = None
            
        if X_test is not None:
            X_test_scaled = X_test.copy()
            X_test_scaled[numeric_cols] = scaler.transform(X_test[numeric_cols])
        else:
            X_test_scaled = None
        
        print("✅ 特征标准化完成")
        return X_train_scaled, X_val_scaled, X_test_scaled
    
    def train_xgboost_regressor(self, X_train: pd.DataFrame, y_train: pd.Series,
                                X_val: pd.DataFrame = None, y_val: pd.Series = None,
                                params: Dict = None) -> xgb.XGBRegressor:
        """
        训练XGBoost回归模型
        
        Args:
            X_train: 训练集特征
            y_train: 训练集标签
            X_val: 验证集特征
            y_val: 验证集标签
            params: 模型参数
            
        Returns:
            训练好的模型
        """
        if not XGBOOST_AVAILABLE:
            raise ImportError("XGBoost未安装")
        
        print("🚀 训练XGBoost回归模型...")
        
        # 默认参数
        default_params = {
            'n_estimators': 100,
            'max_depth': 6,
            'learning_rate': 0.1,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'random_state': 42,
            'n_jobs': -1
        }
        
        if params:
            default_params.update(params)
        
        # 创建模型
        model = xgb.XGBRegressor(**default_params)
        
        # 训练
        if X_val is not None and y_val is not None:
            model.fit(
                X_train, y_train,
                eval_set=[(X_train, y_train), (X_val, y_val)],
                eval_metric='rmse',
                verbose=False
            )
        else:
            model.fit(X_train, y_train)
        
        print("✅ XGBoost回归模型训练完成")
        return model
    
    def train_xgboost_classifier(self, X_train: pd.DataFrame, y_train: pd.Series,
                                 X_val: pd.DataFrame = None, y_val: pd.Series = None,
                                 params: Dict = None) -> xgb.XGBClassifier:
        """
        训练XGBoost分类模型
        
        Args:
            X_train: 训练集特征
            y_train: 训练集标签
            X_val: 验证集特征
            y_val: 验证集标签
            params: 模型参数
            
        Returns:
            训练好的模型
        """
        if not XGBOOST_AVAILABLE:
            raise ImportError("XGBoost未安装")
        
        print("🚀 训练XGBoost分类模型...")
        
        # 默认参数
        default_params = {
            'n_estimators': 100,
            'max_depth': 6,
            'learning_rate': 0.1,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'random_state': 42,
            'n_jobs': -1,
            'eval_metric': 'logloss'
        }
        
        if params:
            default_params.update(params)
        
        # 创建模型
        model = xgb.XGBClassifier(**default_params)
        
        # 训练
        if X_val is not None and y_val is not None:
            model.fit(
                X_train, y_train,
                eval_set=[(X_train, y_train), (X_val, y_val)],
                verbose=False
            )
        else:
            model.fit(X_train, y_train)
        
        print("✅ XGBoost分类模型训练完成")
        return model
    
    def train_lightgbm_regressor(self, X_train: pd.DataFrame, y_train: pd.Series,
                                 X_val: pd.DataFrame = None, y_val: pd.Series = None,
                                 params: Dict = None) -> lgb.LGBMRegressor:
        """
        训练LightGBM回归模型
        
        Args:
            X_train: 训练集特征
            y_train: 训练集标签
            X_val: 验证集特征
            y_val: 验证集标签
            params: 模型参数
            
        Returns:
            训练好的模型
        """
        if not LIGHTGBM_AVAILABLE:
            raise ImportError("LightGBM未安装")
        
        print("🚀 训练LightGBM回归模型...")
        
        # 默认参数
        default_params = {
            'n_estimators': 100,
            'max_depth': 6,
            'learning_rate': 0.1,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'random_state': 42,
            'n_jobs': -1,
            'verbose': -1
        }
        
        if params:
            default_params.update(params)
        
        # 创建模型
        model = lgb.LGBMRegressor(**default_params)
        
        # 训练
        if X_val is not None and y_val is not None:
            model.fit(
                X_train, y_train,
                eval_set=[(X_train, y_train), (X_val, y_val)],
                eval_metric='rmse',
                callbacks=[lgb.early_stopping(stopping_rounds=10), lgb.log_evaluation(0)]
            )
        else:
            model.fit(X_train, y_train)
        
        print("✅ LightGBM回归模型训练完成")
        return model
    
    def train_lightgbm_classifier(self, X_train: pd.DataFrame, y_train: pd.Series,
                                  X_val: pd.DataFrame = None, y_val: pd.Series = None,
                                  params: Dict = None) -> lgb.LGBMClassifier:
        """
        训练LightGBM分类模型
        
        Args:
            X_train: 训练集特征
            y_train: 训练集标签
            X_val: 验证集特征
            y_val: 验证集标签
            params: 模型参数
            
        Returns:
            训练好的模型
        """
        if not LIGHTGBM_AVAILABLE:
            raise ImportError("LightGBM未安装")
        
        print("🚀 训练LightGBM分类模型...")
        
        # 默认参数
        default_params = {
            'n_estimators': 100,
            'max_depth': 6,
            'learning_rate': 0.1,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'random_state': 42,
            'n_jobs': -1,
            'verbose': -1
        }
        
        if params:
            default_params.update(params)
        
        # 创建模型
        model = lgb.LGBMClassifier(**default_params)
        
        # 训练
        if X_val is not None and y_val is not None:
            model.fit(
                X_train, y_train,
                eval_set=[(X_train, y_train), (X_val, y_val)],
                eval_metric='logloss',
                callbacks=[lgb.early_stopping(stopping_rounds=10), lgb.log_evaluation(0)]
            )
        else:
            model.fit(X_train, y_train)
        
        print("✅ LightGBM分类模型训练完成")
        return model
    
    def evaluate_regression(self, model, X: pd.DataFrame, y: pd.Series, 
                           label_name: str = '') -> Dict:
        """
        评估回归模型
        
        Args:
            model: 训练好的模型
            X: 特征
            y: 真实标签
            label_name: 标签名称
            
        Returns:
            评估指标字典
        """
        y_pred = model.predict(X)
        
        mae = mean_absolute_error(y, y_pred)
        rmse = np.sqrt(mean_squared_error(y, y_pred))
        r2 = r2_score(y, y_pred)
        
        # 计算方向准确率（预测涨跌方向是否正确）
        direction_acc = accuracy_score(
            (y > 0).astype(int),
            (y_pred > 0).astype(int)
        )
        
        metrics = {
            'MAE': mae,
            'RMSE': rmse,
            'R²': r2,
            'Direction_Accuracy': direction_acc
        }
        
        if label_name:
            print(f"\n📊 {label_name} 回归模型评估:")
        else:
            print(f"\n📊 回归模型评估:")
        print(f"   MAE: {mae:.4f}")
        print(f"   RMSE: {rmse:.4f}")
        print(f"   R²: {r2:.4f}")
        print(f"   方向准确率: {direction_acc:.4f}")
        
        return metrics
    
    def evaluate_classification(self, model, X: pd.DataFrame, y: pd.Series,
                               label_name: str = '') -> Dict:
        """
        评估分类模型
        
        Args:
            model: 训练好的模型
            X: 特征
            y: 真实标签
            label_name: 标签名称
            
        Returns:
            评估指标字典
        """
        y_pred = model.predict(X)
        y_pred_proba = model.predict_proba(X)[:, 1] if hasattr(model, 'predict_proba') else None
        
        accuracy = accuracy_score(y, y_pred)
        precision = precision_score(y, y_pred, zero_division=0)
        recall = recall_score(y, y_pred, zero_division=0)
        f1 = f1_score(y, y_pred, zero_division=0)
        
        metrics = {
            'Accuracy': accuracy,
            'Precision': precision,
            'Recall': recall,
            'F1': f1
        }
        
        # 如果有概率预测，计算AUC
        if y_pred_proba is not None and len(np.unique(y)) == 2:
            try:
                auc = roc_auc_score(y, y_pred_proba)
                metrics['AUC'] = auc
            except:
                pass
        
        if label_name:
            print(f"\n📊 {label_name} 分类模型评估:")
        else:
            print(f"\n📊 分类模型评估:")
        print(f"   准确率: {accuracy:.4f}")
        print(f"   精确率: {precision:.4f}")
        print(f"   召回率: {recall:.4f}")
        print(f"   F1分数: {f1:.4f}")
        if 'AUC' in metrics:
            print(f"   AUC: {metrics['AUC']:.4f}")
        
        return metrics
    
    def save_model(self, model, model_name: str, label_name: str = ''):
        """
        保存模型
        
        Args:
            model: 训练好的模型
            model_name: 模型名称
            label_name: 标签名称
        """
        if label_name:
            filename = f"{model_name}_{label_name}.pkl"
        else:
            filename = f"{model_name}.pkl"
        
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, 'wb') as f:
            pickle.dump(model, f)
        
        print(f"💾 模型已保存: {filepath}")
    
    def save_metadata(self, metadata: Dict):
        """
        保存元数据
        
        Args:
            metadata: 元数据字典
        """
        filepath = os.path.join(self.output_dir, 'metadata.json')
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2, default=str)
        
        print(f"💾 元数据已保存: {filepath}")
    
    def plot_feature_importance(self, model, model_name: str, label_name: str = '', 
                                top_n: int = 20):
        """
        绘制特征重要性
        
        Args:
            model: 训练好的模型
            model_name: 模型名称
            label_name: 标签名称
            top_n: 显示前N个重要特征
        """
        if not PLOTTING_AVAILABLE:
            return
        
        try:
            # 获取特征重要性
            if hasattr(model, 'feature_importances_'):
                importances = model.feature_importances_
            elif hasattr(model, 'get_feature_importance'):
                importances = model.get_feature_importance()
            else:
                print("⚠️ 模型不支持特征重要性")
                return
            
            # 创建DataFrame
            feature_importance_df = pd.DataFrame({
                'feature': self.feature_names,
                'importance': importances
            }).sort_values('importance', ascending=False).head(top_n)
            
            # 绘图
            plt.figure(figsize=(10, 8))
            sns.barplot(data=feature_importance_df, y='feature', x='importance')
            plt.title(f'{model_name} - {label_name} 特征重要性 (Top {top_n})')
            plt.xlabel('重要性')
            plt.tight_layout()
            
            # 保存图片
            if label_name:
                filename = f"{model_name}_{label_name}_feature_importance.png"
            else:
                filename = f"{model_name}_feature_importance.png"
            
            filepath = os.path.join(self.output_dir, filename)
            plt.savefig(filepath, dpi=300, bbox_inches='tight')
            plt.close()
            
            print(f"📊 特征重要性图已保存: {filepath}")
            
        except Exception as e:
            print(f"⚠️ 绘制特征重要性失败: {e}")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='训练股票预测模型')
    parser.add_argument('--data_file', type=str, default='test_sample.csv', 
                       help='训练数据CSV文件路径')
    parser.add_argument('--output_dir', type=str, default='models', 
                       help='模型输出目录')
    parser.add_argument('--train_end', type=str, default='2023-12-31', 
                       help='训练集结束日期 (YYYY-MM-DD)')
    parser.add_argument('--val_end', type=str, default='2024-12-31', 
                       help='验证集结束日期 (YYYY-MM-DD)')
    parser.add_argument('--model_type', type=str, default='xgboost', 
                       choices=['xgboost', 'lightgbm', 'both'],
                       help='模型类型')
    parser.add_argument('--scale_method', type=str, default='standard',
                       choices=['standard', 'minmax', 'none'],
                       help='特征标准化方法')
    parser.add_argument('--labels', type=str, nargs='+', 
                       default=['return_1d', 'is_rising_1d'],
                       help='要训练的标签列表')
    
    args = parser.parse_args()
    
    # 创建训练器
    trainer = StockModelTrainer(args.data_file, args.output_dir)
    
    # 加载数据
    df = trainer.load_data()
    
    # 预处理
    df = trainer.preprocess_data(df)
    
    # 准备特征和标签
    X, labels = trainer.prepare_features_and_labels(df)
    
    # 按时间划分数据
    train_df, val_df, test_df = trainer.split_data_by_time(
        df, 
        train_end=args.train_end,
        val_end=args.val_end
    )
    
    # 准备训练/验证/测试集的特征和标签
    X_train = train_df[trainer.feature_names]
    X_val = val_df[trainer.feature_names]
    X_test = test_df[trainer.feature_names]
    
    # 特征标准化
    if args.scale_method != 'none':
        X_train, X_val, X_test = trainer.scale_features(
            X_train, X_val, X_test, method=args.scale_method
        )
    
    # 训练模型
    all_results = {}
    
    for label_name in args.labels:
        if label_name not in labels:
            print(f"⚠️ 标签 {label_name} 不存在，跳过")
            continue
        
        print(f"\n{'='*60}")
        print(f"训练标签: {label_name}")
        print(f"{'='*60}")
        
        y_train = labels[label_name][train_df.index]
        y_val = labels[label_name][val_df.index]
        y_test = labels[label_name][test_df.index]
        
        # 移除缺失值
        train_mask = ~(y_train.isna() | X_train.isna().any(axis=1))
        val_mask = ~(y_val.isna() | X_val.isna().any(axis=1))
        test_mask = ~(y_test.isna() | X_test.isna().any(axis=1))
        
        X_train_clean = X_train[train_mask]
        y_train_clean = y_train[train_mask]
        X_val_clean = X_val[val_mask]
        y_val_clean = y_val[val_mask]
        X_test_clean = X_test[test_mask]
        y_test_clean = y_test[test_mask]
        
        print(f"训练集: {len(X_train_clean)} 条")
        print(f"验证集: {len(X_val_clean)} 条")
        print(f"测试集: {len(X_test_clean)} 条")
        
        # 判断是回归还是分类任务
        is_classification = label_name.startswith('is_')
        
        # 训练XGBoost
        if args.model_type in ['xgboost', 'both']:
            if is_classification:
                model = trainer.train_xgboost_classifier(
                    X_train_clean, y_train_clean,
                    X_val_clean, y_val_clean
                )
                metrics = trainer.evaluate_classification(
                    model, X_test_clean, y_test_clean, label_name
                )
            else:
                model = trainer.train_xgboost_regressor(
                    X_train_clean, y_train_clean,
                    X_val_clean, y_val_clean
                )
                metrics = trainer.evaluate_regression(
                    model, X_test_clean, y_test_clean, label_name
                )
            
            trainer.save_model(model, 'xgboost', label_name)
            trainer.plot_feature_importance(model, 'xgboost', label_name)
            all_results[f'xgboost_{label_name}'] = metrics
        
        # 训练LightGBM
        if args.model_type in ['lightgbm', 'both']:
            if is_classification:
                model = trainer.train_lightgbm_classifier(
                    X_train_clean, y_train_clean,
                    X_val_clean, y_val_clean
                )
                metrics = trainer.evaluate_classification(
                    model, X_test_clean, y_test_clean, label_name
                )
            else:
                model = trainer.train_lightgbm_regressor(
                    X_train_clean, y_train_clean,
                    X_val_clean, y_val_clean
                )
                metrics = trainer.evaluate_regression(
                    model, X_test_clean, y_test_clean, label_name
                )
            
            trainer.save_model(model, 'lightgbm', label_name)
            trainer.plot_feature_importance(model, 'lightgbm', label_name)
            all_results[f'lightgbm_{label_name}'] = metrics
    
    # 保存元数据
    metadata = {
        'feature_names': trainer.feature_names,
        'label_names': trainer.label_names,
        'train_end': args.train_end,
        'val_end': args.val_end,
        'scale_method': args.scale_method,
        'model_type': args.model_type,
        'results': all_results,
        'created_at': datetime.now().isoformat()
    }
    trainer.save_metadata(metadata)
    
    print(f"\n{'='*60}")
    print("✅ 模型训练完成！")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()

