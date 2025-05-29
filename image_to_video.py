import cv2
import os
import glob

# setup the parameters
image_folder = "gold_gun_mkreal_wia/output"  # change to your image folder path
# match the image file pattern
# （e.g. render_000.png, render_001.png...）
image_pattern = "render_*.png"
output_video = "output_video.mp4"      # output video file name
fps = 1                               # frames per second

# get all images in the folder matching the pattern
images = sorted(glob.glob(os.path.join(image_folder, image_pattern)))

# check if images are found
if not images:
    raise FileNotFoundError(
        f"No images found in {image_folder} with pattern {image_pattern}")

# read the first image to get dimensions
first_image = cv2.imread(images[0])
height, width, _ = first_image.shape

# create a VideoWriter object
fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # 或使用 'avc1'（H.264）
video = cv2.VideoWriter(output_video, fourcc, fps, (width, height))

# write each image to the video
for image_path in images:
    frame = cv2.imread(image_path)
    video.write(frame)

# release the video writer and close all windows
video.release()
cv2.destroyAllWindows()

print(f"Video saved to: {output_video}")
