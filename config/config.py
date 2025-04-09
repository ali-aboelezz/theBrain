from pathlib import Path
from dataclasses import dataclass
import os 

@dataclass
class FilePaths():
    script_path: str = Path(__file__).resolve()
    paper_seg_model : str = script_path.parents[1] / 'similified_model_paper_seg.onnx'
    data_base_path: str = script_path.parents[1] / 'src/assests/data/'

    def __post_init__(self):
        self.script_path = str(self.script_path)
        self.paper_seg_model = str(self.paper_seg_model)
        self.data_base_path = str(self.data_base_path)

file_paths = FilePaths()
print(file_paths.script_path)
print(file_paths.paper_seg_model)