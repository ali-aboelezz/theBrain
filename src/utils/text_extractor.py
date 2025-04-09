
from cnocr import CnOcr
import numpy as np 
from typing import Optional

class TextImgExtractor():

    def __init__(self, detection_model_name:str = "en_PP-OCRv3_det", 
                 rec_model_name:str ="n_number_mobile_v2.0"):
        
        self.ocr = CnOcr(det_model_name='en_PP-OCRv3_det', rec_model_name='en_number_mobile_v2.0')

        # self.ocr = CnOcr(det_model_name=detection_model_name, 
        #                  rec_model_name=rec_model_name)

    def _extract_text(self, outputs:list, scores_indces:Optional[list])->list:
        txts = [line['text'] for line in outputs]
        
        txts = np.array(txts).astype(str)
        indeces = np.array(scores_indces)

        return txts[indeces]

    def _extract_boxes(self, outputs:list, scores_indces:Optional[list])-> list:
        boxes = [line['position'] for line in outputs]

        boxes = np.array(boxes)
        indeces = np.array(scores_indces)

        return boxes[indeces]

    def _extract_scores(self, outputs:list, threshold:float = 0.5)-> tuple[list, list]: 
        scores = [line['score'] for line in outputs if line['score'] > threshold]

        scores, indences = [],[]

        for index, line in enumerate(outputs): 

            if line['score']  > threshold: 
                indences.append(index)
                scores.append(line['score'])


        return scores, indences
        
    def extract(self, img: np.ndarray, 
                     return_boxes: bool =False, 
                     return_scors:bool = False, 
                     return_texts:bool = True, 
                     score_threshold:float = 0.0):
        
        texts, boxes, scores = None, None, None

        output = self.ocr.ocr(img)

        thresh_score, indces = self._extract_scores(outputs=output, threshold=score_threshold)

        if return_scors: 
            scores = thresh_score

        if return_boxes: 
            boxes = self._extract_boxes(outputs=output, scores_indces=indces)

        if return_texts: 
            texts = self._extract_text(output, scores_indces=indces)

        return texts, boxes, scores
    

if __name__ == "__main__":
    from image_handler import ImageHandler

    text_extractor = TextImgExtractor()

    img = ImageHandler.read_img('/home/azooz/mydisk/ocr_invoices/imgs/254.jpg', return_numpy=True)

    print(img.shape)
    texts,_,_ = text_extractor.ocr_img_text(img, score_threshold=0.5)
    print(texts)        

