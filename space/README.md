---
title: Plant Disease Detection
emoji: 🌿
colorFrom: green
colorTo: gray
sdk: static
app_file: index.html
pinned: false
short_description: Detect 23 plant leaf diseases with a ResNet18 model
---

# Plant Disease Detection using Deep Learning

Upload a leaf photo and the app identifies the crop and disease (23 PlantVillage classes across apple,
corn, bell pepper, potato and tomato), shows confidence and top-3 predictions, estimates the affected
leaf area and suggests treatment.

- **Model:** ResNet18 (ImageNet pretrained) fine-tuned with PyTorch (transfer learning)
- **Inference:** exported to ONNX and run in the browser with ONNX Runtime Web, so images never leave your device
- **Severity:** HSV colour segmentation of leaf tissue vs. discoloured lesions

Source: https://github.com/Praneethchowdary07/Plant-Disease-Detection

Educational demo. Yield figures are rough estimates.
