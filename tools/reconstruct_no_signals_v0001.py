"""Create the last missing JSON using its movie's embedded AE project link."""
import reconstruct_bg_v0001 as reconstruction

reconstruction.VERSION = 'X:/Cytonics_CYT108/03_Production/Shots/SQ030/SH020/Renders/2dRender/No_Signals/v0001'
reconstruction.SOURCE = ('X:/Cytonics_CYT108/03_Production/Shots/SQ030/SH020/Scenefiles/'
                         'LookDev/LowRes/SQ030-SH020_LowRes_v0012.aep')
reconstruction.MOVIE = reconstruction.VERSION + '/SQ030-SH020_No_Signals_v0001.mov'
reconstruction.COMPOSITION_ID = '113'
reconstruction.COMPOSITION_NAME = 'SQ030-SH020_LowRes_v0001'
reconstruction.RECORD_FILE = 'cytonics-no-signals-v0001-reconstruction.json'

if __name__ == '__main__':
    reconstruction.main()
