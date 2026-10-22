"""Exercise the real Windows SDL renderer at a naturally reached perch."""
import os
os.environ['SDL_VIDEODRIVER']='windows'
os.environ.setdefault('NUMBA_NUM_THREADS','4')
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import json
import pygame
from game.app import App
from game.session import load_config


def main():
    out=ROOT/'artifacts/m1_8_a';out.mkdir(exist_ok=True)
    app=App(load_config(ROOT/'game_room_config.json'),seed=255,mode='evaluation')
    app.pointer_world=(1920,388.8)
    try:
        for _ in range(240):
            pygame.event.pump()
            app._advance(.02,False)
        assert app.session.world.lifecycle.stationary
        app._draw()
        pygame.image.save(app.canvas,str(out/'windows-perched-windowed.png'))
        sizes={'windowed':list(app.screen.get_size())}
        app._toggle_fullscreen();app._draw()
        pygame.image.save(app.screen,str(out/'windows-perched-fullscreen.png'))
        sizes['fullscreen']=list(app.screen.get_size())
        app._toggle_fullscreen();app._draw()
        result={'driver':pygame.display.get_driver(),'sizes':sizes,'mode':app.session.world.lifecycle.mode,
                'speed':app.session.world.body_lengths_per_second,'ticks':app.session.ticks,
                'returned_windowed_size':list(app.screen.get_size()),'rendered':True}
        (out/'windows-render.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result))
    finally:
        app.session.close();pygame.quit()


if __name__=='__main__':main()
