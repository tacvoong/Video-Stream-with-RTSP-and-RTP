import io
import imageio, imageio_ffmpeg
from PIL import Image
class VideoStream:
        def __init__(self, filename):
                self.filename = filename
                self.file = imageio.get_reader(filename)
                self.frameNum = 0
                
        def nextFrame(self):
                """Get next frame."""
                self.frameNum += 1
                data = self.file.get_next_data()
                frame_image = Image.fromarray(data)
                
                buf = io.BytesIO()
                frame_image.save(buf, format='JPEG')
                return buf.getvalue()
                
        def frameNbr(self):
                """Get frame number."""
                return self.frameNum

        def frameCount(self):
                """Get frame count. Imageio's get_length doesn't work on ffmpeg formats by default"""
                return self.file.count_frames()

        def seek(self, idx):
                """Seek to this frame"""
                self.file.set_image_index(idx)
                self.frameNum = idx-1
                print("VideoStream index set to",idx)
