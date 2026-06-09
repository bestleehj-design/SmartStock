#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模型预测脚本
使用训练好的模型进行股票预测
"""

import os
import sys
import pickle
import json
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import argparse


class StockPredictor:
    """股票预测器"""
    
    def __init__(self, model_dir: str = 'models'):
        """
        初始化预测器
        
        Args:
            model_dir: 模型目录
        """
        self.model_dir = model_dir
        self.models = {}
        self.scalers = {}
        self.metadata = None
        self.feature_names = []
        
        # 加载元数据
        self._load_metadata()
    
    def _load_metadata(self):
        """加载元数据"""
        metadata_path = os.path.join(self.model_dir, 'metadata.json')
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r', encoding='utf-8') as f:
                self.metadata = json.load(f)
                self.feature_names = self.metadata.get('feature_names', [])
                print(f"✅ 加载元数据，特征数量: {len(self.feature_names)}")
        else:
            print("⚠️ 元数据文件不存在")
    
    def load_model(self, model_name: str, label_name: str):
        """
        加载模型
        
        Args:
            model_name: 模型名称（xgboost 或 lightgbm）
            label_name: 标签名称
        """
        filename = f"{model_name}_{label_name}.pkl"
        filepath = os.path.join(self.model_dir, filename)
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"模型文件不存在: {filepath}")
        
        with open(filepath, 'rb') as f:
            model = pickle.load(f)
        
        key = f"{model_name}_{label_name}"
        self.models[key] = model
        
        print(f"✅ 加载模型: {key}")
        return model
    
    def load_scaler(self, scale_method: str = 'standard'):
        """
        加载特征标准化器
        
        Args:
            scale_method: 标准化方法
        """
        # 注意：scaler可能没有保存，需要从metadata中获取信息
        # 这里只是占位，实际使用时可能需要重新训练scaler或使用保存的scaler
        pass
    
    def prepare_features(self, data: Dict) -> pd.DataFrame:
        """
        准备特征数据
        
        Args:
            data: 特征数据字典
            
        Returns:
            特征DataFrame
        """
        if not self.feature_names:
            raise ValueError("特征名称未加载，请先加载元数据")
        
        # 创建特征DataFrame
        features = {}
        for feature_name in self.feature_names:
            if feature_name in data:
                features[feature_name] = [data[feature_name]]
            else:
                # 如果特征缺失，使用默认值
                features[feature_name] = [0]
                print(f"⚠️ 特征 {feature_name} 缺失，使用默认值0")
        
        return pd.DataFrame(features)
    
    def predict(self, features: pd.DataFrame, model_name: str, label_name: str) -> np.ndarray:
        """
        进行预测
        
        Args:
            features: 特征DataFrame
            model_name: 模型名称
            label_name: 标签名称
            
        Returns:
            预测结果
        """
        key = f"{model_name}_{label_name}"
        
        if key not in self.models:
            self.load_model(model_name, label_name)
        
        model = self.models[key]
        
        # 确保特征顺序正确
        features = features[self.feature_names]
        
        # 预测
        predictions = model.predict(features)
        
        return predictions
    
    def predict_proba(self, features: pd.DataFrame, model_name: str, label_name: str) -> np.ndarray:
        """
        进行概率预测（分类模型）
        
        Args:
            features: 特征DataFrame
            model_name: 模型名称
            label_name: 标签名称
            
        Returns:
            预测概率
        """
        key = f"{model_name}_{label_name}"
        
        if key not in self.models:
            self.load_model(model_name, label_name)
        
        model = self.models[key]
        
        # 确保特征顺序正确
        features = features[self.feature_names]
        
        # 预测概率
        if hasattr(model, 'predict_proba'):
            probabilities = model.predict_proba(features)
            return probabilities
        else:
            raise ValueError(f"模型 {key} 不支持概率预测")
    
    def batch_predict(self, features_list: List[Dict], model_name: str, label_name: str) -> np.ndarray:
        """
        批量预测
        
        Args:
            features_list: 特征数据列表
            model_name: 模型名称
            label_name: 标签名称
            
        Returns:
            预测结果数组
        """
        # 准备所有特征
        all_features = []
        for data in features_list:
            features_df = self.prepare_features(data)
            all_features.append(features_df)
        
        # 合并
        combined_features = pd.concat(all_features, ignore_index=True)
        
        # 预测
        predictions = self.predict(combined_features, model_name, label_name)
        
        return predictions


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='使用训练好的模型进行预测')
    parser.add_argument('--model_dir', type=str, default='models',
                       help='模型目录')
    parser.add_argument('--model_name', type=str, default='xgboost',
                       choices=['xgboost', 'lightgbm'],
                       help='模型名称')
    parser.add_argument('--label_name', type=str, required=True,
                       help='标签名称（如 return_1d, is_rising_1d）')
    parser.add_argument('--input_file', type=str,
                       help='输入CSV文件路径（包含特征数据）')
    parser.add_argument('--output_file', type=str,
                       help='输出CSV文件路径（预测结果）')
    
    args = parser.parse_args()
    
    # 创建预测器
    predictor = StockPredictor(args.model_dir)
    
    # 加载模型
    predictor.load_model(args.model_name, args.label_name)
    
    # 从文件读取特征数据
    if args.input_file:
        print(f"📥 从文件加载特征: {args.input_file}")
        df = pd.read_csv(args.input_file, encoding='utf-8-sig')
        
        # 准备特征
        features = df[predictor.feature_names]
        
        # 预测
        predictions = predictor.predict(features, args.model_name, args.label_name)
        
        # 保存结果
        result_df = df.copy()
        result_df[f'predicted_{args.label_name}'] = predictions
        
        if args.output_file:
            result_df.to_csv(args.output_file, index=False, encoding='utf-8-sig')
            print(f"💾 预测结果已保存: {args.output_file}")
        else:
            print("\n预测结果:")
            print(result_df[['code', 'date', f'predicted_{args.label_name}']].head(10))
    else:
        # 示例：使用单个样本预测
        print("📝 使用示例数据进行预测...")
        
        # 示例特征数据（需要根据实际特征调整）
        sample_data = {
            'strategy1_score': 5,
            'ma_convergence_ratio': 0.03,
            'volume_ratio': 1.8,
            'trend_type': 'uptrend',
            'trend_confidence': 0.8,
            'trend_score': 7,
            'strategy3_score': 8,
            'macd_dif': 0.1,
            'macd_dea': 0.05,
            'macd_bar': 0.05,
            'macd_golden_cross': 1,
            'macd_red_bar_expanding': 1,
            'kdj_k': 65,
            'kdj_d': 60,
            'kdj_j': 75,
            'kdj_low_golden_cross': 0,
            'rsi_value': 65,
            'rsi_above_50': 1,
            'rsi_upward': 1,
            'chip_concentration_ratio': 0.5,
            'upper_pressure_ratio': 0.3,
            'ma5': 10.5,
            'ma10': 10.3,
            'ma30': 10.1,
            'ma5_ma10_ratio': 1.02,
            'current_price': 10.5,
            'change_pct': 3.5,
            'price_volatility': 2.0,
            'today_net_inflow': 5000,
            'continuous_inflow_days': 3,
            'total_net_inflow': 15000,
            'turnover_rate': 2.5,
            'circ_mv': 1000
        }
        
        # 准备特征
        features = predictor.prepare_features(sample_data)
        
        # 预测
        prediction = predictor.predict(features, args.model_name, args.label_name)
        
        print(f"\n预测结果 ({args.label_name}):")
        print(f"  预测值: {prediction[0]:.4f}")
        
        # 如果是分类任务，显示概率
        if args.label_name.startswith('is_'):
            try:
                proba = predictor.predict_proba(features, args.model_name, args.label_name)
                print(f"  预测概率: {proba[0]}")
            except:
                pass


if __name__ == '__main__':
    main()

