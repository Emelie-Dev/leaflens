# Plant Disease Detection using Deep Learning

AI-powered plant disease detection from leaf images. A **ResNet18** CNN (transfer learning, PyTorch) classifies
**23 classes** across apple, corn, bell pepper, potato and tomato, and a Flask web app reports the disease,
confidence, top-3 predictions, affected leaf area and recommended treatment.

**Live demo:** https://huggingface.co/spaces/Praneeth9392/plant-disease-detection

| Item | Detail |
|---|---|
| Model | ResNet18, ImageNet-pretrained, fine-tuned (head first, then full network) |
| Data | PlantVillage, 23 classes, 80/20 train/validation split |
| Result | 98.5% validation accuracy (original training run in `finalprojectcode.ipynb`) |
| Serving | ONNX Runtime Web in the browser (`space/`, Hugging Face Static Space) or ONNX Runtime in a Flask app (`webapp/`) |

## Repository

- `finalprojectcode.ipynb` — original training + Flask app notebook
- `train_plant_model.ipynb` — reproducible Colab notebook: downloads PlantVillage, trains ResNet18 on a free GPU, exports ONNX, uploads to the Space
- `space/` — the live demo: static site that runs the ONNX model in the browser (Hugging Face Static Space; example images come from `webapp/static/examples/`)
- `webapp/` — the same app as a Flask server (Docker), for running locally

## Run the web app locally

```bash
cd webapp
pip install -r requirements.txt
# put plant_resnet18.onnx, class_names.json, metrics.json (from the Colab notebook) in webapp/model/
python app.py   # http://localhost:7860
```
