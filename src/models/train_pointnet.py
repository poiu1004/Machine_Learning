import os
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics import classification_report, accuracy_score, f1_score, roc_auc_score
from pointnet import ProteinPointCloudDataset, PointNetCls
from tqdm import tqdm

DATA_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed", "features.csv"))
FIGURES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "figures"))
MODEL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "models"))

def train_pointnet():
    if not os.path.exists(FIGURES_DIR): os.makedirs(FIGURES_DIR)
    if not os.path.exists(MODEL_DIR): os.makedirs(MODEL_DIR)

    # 1. Exactly match the Target-Level Split from Baseline
    train_targets = ['1fc2', '2cro', '4icb']
    test_targets = ['1hdd-C']
    
    print(f"Train Targets: {train_targets}")
    print(f"Test Targets : {test_targets}")

    # 2. Setup DataLoaders
    train_dataset = ProteinPointCloudDataset(DATA_PATH, target_list=train_targets, num_points=128)
    test_dataset = ProteinPointCloudDataset(DATA_PATH, target_list=test_targets, num_points=128)
    
    train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True, num_workers=0)
    test_loader = DataLoader(test_dataset, batch_size=32, shuffle=False, num_workers=0)
    
    print(f"Train size: {len(train_dataset)}, Test size: {len(test_dataset)}")
    
    # 3. Calculate Class Weights for Imbalanced Data
    labels = [row['label'] for row in train_dataset.data]
    class_counts = np.bincount(labels)
    total_samples = len(labels)
    # class_weight = total_samples / (num_classes * count)
    class_weights = total_samples / (2.0 * class_counts)
    class_weights = torch.tensor(class_weights, dtype=torch.float32)
    print(f"Class Weights (Stable vs Defective): {class_weights.numpy()}")

    # 4. Setup Model, Loss, Optimizer
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    
    model = PointNetCls(num_classes=2).to(device)
    criterion = nn.CrossEntropyLoss(weight=class_weights.to(device))
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    
    # 5. Training Loop
    epochs = 20
    train_losses = []
    test_aucs = []
    
    for epoch in range(epochs):
        model.train()
        running_loss = 0.0
        
        for points, labels in tqdm(train_loader, desc=f"Epoch {epoch+1}/{epochs}"):
            points, labels = points.to(device), labels.to(device)
            
            optimizer.zero_grad()
            logits, _, _ = model(points)
            loss = criterion(logits, labels)
            
            loss.backward()
            optimizer.step()
            
            running_loss += loss.item() * points.size(0)
            
        epoch_loss = running_loss / len(train_dataset)
        train_losses.append(epoch_loss)
        
        # Validation
        model.eval()
        all_preds = []
        all_probs = []
        all_labels = []
        
        with torch.no_grad():
            for points, labels in test_loader:
                points, labels = points.to(device), labels.to(device)
                logits, _, _ = model(points)
                
                probs = torch.softmax(logits, dim=1)[:, 1] # Probability of class 1 (Defective)
                preds = torch.argmax(logits, dim=1)
                
                all_probs.extend(probs.cpu().numpy())
                all_preds.extend(preds.cpu().numpy())
                all_labels.extend(labels.cpu().numpy())
                
        # Handle case where test set might have only 1 class in some strict splits
        try:
            auc = roc_auc_score(all_labels, all_probs)
        except ValueError:
            auc = 0.5
            
        test_aucs.append(auc)
        acc = accuracy_score(all_labels, all_preds)
        f1 = f1_score(all_labels, all_preds, zero_division=0)
        
        print(f"Epoch {epoch+1} | Loss: {epoch_loss:.4f} | Test Acc: {acc:.4f} | Test F1: {f1:.4f} | Test AUC: {auc:.4f}")
        
    print("\n[Final PointNet Classification Report on Unseen Target]")
    print(classification_report(all_labels, all_preds, zero_division=0))
    
    # Save Model
    torch.save(model.state_dict(), os.path.join(MODEL_DIR, "pointnet.pth"))
    
    # Plot Training Curves
    plt.figure(figsize=(10, 4))
    plt.subplot(1, 2, 1)
    plt.plot(range(1, epochs+1), train_losses, marker='o', color='red')
    plt.title("PointNet Training Loss")
    plt.xlabel("Epoch")
    plt.ylabel("CrossEntropy Loss")
    
    plt.subplot(1, 2, 2)
    plt.plot(range(1, epochs+1), test_aucs, marker='o', color='blue')
    plt.title("PointNet Test ROC-AUC (Unseen Target)")
    plt.xlabel("Epoch")
    plt.ylabel("ROC-AUC")
    
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "pointnet_training_curves.png"))
    print("Training complete! Model and curves saved.")

if __name__ == "__main__":
    train_pointnet()
