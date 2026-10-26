---
title: Plant Disease Detection
emoji: 🌿
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: Detect 23 plant leaf diseases with a ResNet18 model
---

# Plant Disease Detection using Deep Learning

Upload a leaf photo and the app identifies the crop and disease (23 PlantVillage classes across apple,
corn, bell pepper, potato and tomato), shows confidence and top-3 predictions, estimates the affected
leaf area, and suggests treatment.

- **Model:** ResNet18 (ImageNet pretrained) fine-tuned with PyTorch — transfer learning
- **Serving:** exported to ONNX and run with ONNX Runtime on CPU (fast, small image)
- **Severity:** HSV colour segmentation of leaf tissue vs. discoloured lesions
- **Web:** Flask + vanilla JS

Model files live in `model/` (`plant_resnet18.onnx`, `class_names.json`, `metrics.json`) and are
produced by `train_plant_model.ipynb` (Google Colab, free GPU).

Educational demo — yield figures are rough estimates.
