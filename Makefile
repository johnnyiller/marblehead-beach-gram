.PHONY: install sample generate list-backgrounds backgrounds reel-script reel post-dry post-reel-dry clean

install:
	pip install -r requirements.txt

sample:
	python scripts/generate.py --sample

generate:
	python scripts/generate.py

list-backgrounds:
	python scripts/generate.py --list-art-directions

backgrounds:
	python scripts/generate.py --sample --background-variants 6

reel-script:
	python scripts/generate_reel.py --print-script

reel:
	python scripts/generate_reel.py

post-dry:
	DRY_RUN=true python scripts/post_instagram.py

post-reel-dry:
	DRY_RUN=true python scripts/post_instagram.py --media-type reel

clean:
	rm -f site/latest.png site/latest.jpg site/latest.json site/latest-reel.png site/latest-reel.jpg site/latest-reel.mp4 site/latest-reel-audio.mp3 site/reel-preview.html
	rm -f site/assets/tidegram-*.png site/assets/tidegram-*.jpg site/assets/tidegram-*.mp4 site/assets/tidegram-*.mp3
