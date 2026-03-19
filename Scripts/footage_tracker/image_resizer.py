# -*- coding: utf-8 -*-
"""
Image Resizer Module
Handles batch image resizing operations with AOV-aware interpolation
"""

import os
import shutil
import re
import sys
import json
from datetime import datetime

# Add local lib directory to Python path BEFORE importing PIL/numpy
# This allows packages to be installed locally without system-wide installation
try:
    # Get this file's directory and navigate to AfterEffects folder
    # __file__ is: .../AfterEffects/Scripts/footage_tracker/image_resizer.py
    # Go up 2 levels to get to AfterEffects root: footage_tracker -> Scripts -> AfterEffects
    current_dir = os.path.dirname(os.path.abspath(__file__))
    aftereffects_dir = os.path.dirname(os.path.dirname(current_dir))
    # Try multiple possible lib locations
    possible_libs = [
        os.path.join(aftereffects_dir, "lib", "python311", "site-packages"),
        os.path.join(aftereffects_dir, "lib", "python39", "site-packages"),
        os.path.join(aftereffects_dir, "lib", "python310", "site-packages"),
        os.path.join(aftereffects_dir, "lib", "python312", "site-packages"),
    ]

    for local_lib in possible_libs:
        if os.path.exists(local_lib) and local_lib not in sys.path:
            sys.path.insert(0, local_lib)
            print(f"[DEBUG] Added to sys.path: {local_lib}")  # Debug output

    # Debug: Print where we're looking for OpenImageIO
    print(f"[DEBUG] AfterEffects dir: {aftereffects_dir}")
    for local_lib in possible_libs:
        exists = os.path.exists(local_lib)
        oiio_exists = os.path.exists(os.path.join(local_lib, "OpenImageIO")) if exists else False
        print(f"[DEBUG] {local_lib}: exists={exists}, OpenImageIO={oiio_exists}")

except Exception as e:
    print(f"[DEBUG] Path setup error: {e}")  # Debug output
    import traceback
    print(f"[DEBUG] Traceback: {traceback.format_exc()}")
    pass  # If path setup fails, continue with system paths

from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *

from PrismUtils.Decorators import err_catcher as err_catcher

# Find Prism Python directory and add to path for PIL imports
# Common Prism installation paths
PRISM_PATHS = [
    r"C:\Program Files\Prism2",
    r"C:\Program Files\Prism",
    r"C:\Prism2",
    r"C:\Prism",
]

def get_prism_python_path():
    """Find the Prism Python executable path."""
    import platform

    # Check if we're already in Prism Python environment
    python_exe = sys.executable

    # If current Python is from a Prism folder, use it
    if "Prism" in python_exe or "prism" in python_exe.lower():
        return python_exe

    # Otherwise, search for Prism Python installations
    for prism_base in PRISM_PATHS:
        if os.path.isdir(prism_base):
            # Look for Python folders (Python39, Python310, Python311, Python312)
            for item in os.listdir(prism_base):
                if item.lower().startswith("python"):
                    python_dir = os.path.join(prism_base, item)
                    if os.path.isdir(python_dir):
                        if platform.system() == "Windows":
                            python_exe = os.path.join(python_dir, "python.exe")
                        else:
                            python_exe = os.path.join(python_dir, "bin", "python")

                        if os.path.exists(python_exe):
                            return python_exe
    return None

PRISM_PYTHON = get_prism_python_path()

# Optional import with graceful degradation
try:
    import OpenImageIO as oiio
    OIIO_AVAILABLE = True
    oiio_ver = oiio.__version__ if hasattr(oiio, '__version__') else 'unknown'
    print(f"[DEBUG] OpenImageIO imported successfully: version {oiio_ver}")
except ImportError as e:
    OIIO_AVAILABLE = False
    print(f"[DEBUG] OpenImageIO import failed: {e}")
    # Try alternative import for oiio-python package
    try:
        import oiio
        OIIO_AVAILABLE = True
        print(f"[DEBUG] oiio imported successfully (alternative import)")
    except ImportError:
        print(f"[DEBUG] oiio import also failed")
except Exception as e:
    OIIO_AVAILABLE = False
    print(f"[DEBUG] OpenImageIO unexpected error: {e}")


class ImageResizer(QObject):
    """Handles image resizing operations for AOV folders"""

    # Default filter to use if no rules match
    DEFAULT_FILTER = "lanczos3"

    # Path to ruleset JSON file
    def get_ruleset_path(self):
        """Get the path to the ruleset JSON file"""
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            aftereffects_dir = os.path.dirname(os.path.dirname(current_dir))
            return os.path.join(aftereffects_dir, "rule_sets.json")
        except Exception:
            return None

    def load_ruleset(self):
        """Load the ruleset from JSON file"""
        ruleset_path = self.get_ruleset_path()
        if not ruleset_path or not os.path.exists(ruleset_path):
            print(f"[DEBUG RULESET] No ruleset file found at: {ruleset_path}")
            return None

        try:
            with open(ruleset_path, 'r') as f:
                ruleset = json.load(f)
            print(f"[DEBUG RULESET] Loaded ruleset: {ruleset.get('ruleset', 'unknown')}")
            return ruleset
        except Exception as e:
            print(f"[DEBUG RULESET] Failed to load ruleset: {e}")
            return None

    # AOV pass type classifications for interpolation selection (fallback if no ruleset)
    COLOR_PASSES = {
        'beauty', 'diffuse', 'specular', 'albedo', 'color',
        'reflection', 'refraction', 'emission', 'shadow', 'ao',
        'ambient_occlusion', 'indirect', 'direct', 'transmission',
        'subsurface', 'sss', 'coat', 'sheen'
    }

    DATA_PASSES = {
        'motion', 'motionvector', 'motionvectors', 'velocity', 'speed',
        'depth', 'zdepth', 'z', 'position', 'worldposition', 'pworld',
        'pref', 'camera', 'stencil', 'coverage', 'alpha'
    }

    NORMAL_PASSES = {
        'normal', 'normals', 'nrm', 'worldnormal', 'normalworld',
        'tangent', 'bitangent'
    }

    MASK_PASSES = {
        'mask', 'masks', 'id', 'objectid', 'matid', 'materialid',
        'cryptomatte', 'crypto', 'atom', 'index', 'idbuffer',
        'object', 'material'
    }

    # Resolution presets
    RESOLUTION_PRESETS = {
        'HD': (1280, 720),
        'Full HD': (1920, 1080),
        '4K': (3840, 2160)
    }

    # Supported formats
    SUPPORTED_FORMATS = {'.exr', '.png', '.jpg', '.jpeg', '.tif', '.tiff'}

    def __init__(self, tracker):
        super(ImageResizer, self).__init__()
        self.tracker = tracker
        self.core = tracker.core
        self.utils = tracker.utils

    @err_catcher(name=__name__)
    def detectAOVFromPath(self, file_path):
        """
        Extract AOV name from file path.
        Expected path pattern:
        X:/Project/03_Production/Shots/SQ01/SH010/Renders/3dRender/Lighting/v0010/beauty/filename.exr
                                                                                  ^^^^
        Returns the AOV folder name (e.g., 'beauty', 'motion', 'normal')
        """
        path_normalized = file_path.replace('\\', '/')
        path_parts = path_normalized.split('/')

        # Look for version folder (v####) pattern
        for i, part in enumerate(path_parts):
            if re.match(r'v\d{4}', part):
                # AOV folder is the next part after version folder
                if i + 1 < len(path_parts):
                    aov_name = path_parts[i + 1]
                    return aov_name.lower()

        # Fallback: check if parent folder is AOV (file is directly in AOV folder)
        parent_folder = os.path.dirname(file_path)
        if parent_folder:
            folder_name = os.path.basename(parent_folder)
            # Check if this looks like an AOV name (not a shot or version folder)
            if not re.match(r'(sh|ch|sq|ep)\d+', folder_name.lower()) and \
               not re.match(r'v\d{4}', folder_name):
                return folder_name.lower()

        return None

    @err_catcher(name=__name__)
    def getInterpolationMethod(self, aov_name):
        """
        Determine appropriate interpolation method based on AOV type using ruleset.
        Returns tuple of (OpenImageIO filter string, interpolate: bool, description string).
        """
        if not OIIO_AVAILABLE:
            raise ImportError("OpenImageIO library is required for image resizing. "
                            "Install with: pip install OpenImageIO")

        if not aov_name:
            aov_name = 'unknown'

        # Try to load and use ruleset from JSON file
        ruleset = self.load_ruleset()
        if ruleset:
            filters = ruleset.get('filters', {})
            rules = ruleset.get('rules', [])
            default_filter = ruleset.get('default', {}).get('filter', self.DEFAULT_FILTER)
            default_interpolate = ruleset.get('default', {}).get('interpolate', True)

            # Try each rule in order
            for rule in rules:
                pattern = rule.get('match')
                if pattern:
                    try:
                        if re.search(pattern, aov_name, re.IGNORECASE):
                            apply_filter = rule.get('apply')
                            if apply_filter and apply_filter in filters:
                                filter_config = filters[apply_filter]
                                interpolate = filter_config.get('interpolate', default_interpolate)

                                # Only get filter name if interpolating
                                # (non-interpolating uses resample, no filter needed)
                                if interpolate:
                                    filter_name = filter_config.get('filter', default_filter)
                                else:
                                    filter_name = None

                                print(
                                    f"[DEBUG RULESET] Matched rule '{rule.get('name')}'"
                                    f" for AOV '{aov_name}' -> filter: {filter_name},"
                                    f" interpolate: {interpolate}"
                                )
                                return filter_name, interpolate, f"{apply_filter} (from ruleset)"
                    except re.error as e:
                        print(f"[DEBUG RULESET] Invalid regex pattern '{pattern}': {e}")
                        continue

            # No rule matched, use default
            if default_interpolate:
                print(
                    f"[DEBUG RULESET] No rule matched for AOV '{aov_name}',"
                    f" using default: {default_filter}, interpolate: {default_interpolate}"
                )
                return default_filter, default_interpolate, f"Default ({default_filter})"
            else:
                print(
                    f"[DEBUG RULESET] No rule matched for AOV '{aov_name}',"
                    f" using default: None, interpolate: {default_interpolate}"
                )
                return None, default_interpolate, "Default (no interpolation)"

        # Fallback to simple keyword matching if no ruleset
        print(f"[DEBUG RULESET] Using fallback keyword matching for AOV '{aov_name}'")
        aov_lower = aov_name.lower()

        # Check for color passes - use Lanczos3 (high quality)
        if any(pass_name in aov_lower for pass_name in self.COLOR_PASSES):
            return "lanczos3", True, "Lanczos3"

        # Check for data passes - use linear (preserves data values)
        elif any(pass_name in aov_lower for pass_name in self.DATA_PASSES):
            return "catmull-rom", True, "Catmull-Rom"

        # Check for normal passes - special handling
        elif any(pass_name in aov_lower for pass_name in self.NORMAL_PASSES):
            return "lanczos3", True, "Lanczos3 (will renormalize)"

        # Check for mask/ID passes - use nearest (preserves discrete values)
        elif any(pass_name in aov_lower for pass_name in self.MASK_PASSES):
            return None, False, "Nearest Neighbor (no interpolation)"

        # Default to Lanczos3 for unknown pass types
        return "lanczos3", True, "Lanczos3 (default)"

    @err_catcher(name=__name__)
    def collectAOVFiles(self, file_path):
        """
        Collect all files in the same AOV folder as the given file.
        Returns tuple of (sorted list of file paths, AOV folder path).
        """
        aov_folder = os.path.dirname(file_path)

        if not os.path.isdir(aov_folder):
            return [], None

        files = []
        for item in os.listdir(aov_folder):
            item_path = os.path.join(aov_folder, item)
            if os.path.isfile(item_path):
                ext = os.path.splitext(item)[1].lower()
                if ext in self.SUPPORTED_FORMATS:
                    files.append(item_path)

        return sorted(files), aov_folder

    @err_catcher(name=__name__)
    def isCryptomatte(self, spec):
        """Check if this image spec contains Cryptomatte metadata"""
        # Check for cryptomatte attributes by iterating through extra attributes
        crypto_attrs = ['cryptomatte/manifest', 'cryptomatte/hash', 'cryptomatte/conversion', 'cryptomatte/name']

        # Iterate through all extra attributes in the spec
        for param in spec.extra_attribs:
            attr_name = param.name
            # Check if this is a cryptomatte attribute
            if attr_name in crypto_attrs or attr_name.startswith('cryptomatte'):
                return True

        # Check for cryptomatte in channel names (common pattern: cryptoMaterial, cryptoObject, etc.)
        for i in range(spec.nchannels):
            chan_name = spec.channel_name(i)
            if chan_name and 'crypto' in chan_name.lower():
                return True

        return False

    @err_catcher(name=__name__)
    def resizeImage(self, source_path, target_path, target_size, interpolation, interpolate=True):
        """
        Resize a single image file using OpenImageIO for EXR/Deep EXR compatibility.
        Preserves AOV metadata, channel names, and float data.

        Args:
            source_path: Path to source image
            target_path: Path to save resized image
            target_size: Tuple of (width, height)
            interpolation: OpenImageIO interpolation string (e.g., "lanczos3", "catmull-rom")
            interpolate: If False, use nearest-neighbor resample (for ID passes); if True, use filter

        Returns tuple of (success: bool, error_message: str or None)
        """
        try:
            print(f"[DEBUG RESIZE] Attempting to resize: {source_path}")
            print(f"[DEBUG RESIZE] Target: {target_path}")
            print(f"[DEBUG RESIZE] File exists: {os.path.exists(source_path)}")

            # Check file extension
            ext = os.path.splitext(source_path)[1].lower()
            print(f"[DEBUG RESIZE] File extension: {ext}")

            # Get OpenImageIO module (try both import styles)
            oiio_module = None
            if OIIO_AVAILABLE:
                # Use the module-level import if available
                import sys
                if 'OpenImageIO' in sys.modules:
                    oiio_module = sys.modules['OpenImageIO']
                elif 'oiio' in sys.modules:
                    oiio_module = sys.modules['oiio']

            if oiio_module is None:
                return False, "OpenImageIO is not available. Install with: pip install oiio-python"

            # Read input image using OpenImageIO
            input_buf = oiio_module.ImageBuf(source_path)

            # Get original specs for debugging
            spec = input_buf.spec()
            print(f"[DEBUG RESIZE] Image loaded: {spec.width}x{spec.height}, "
                  f"channels={input_buf.nchannels}, format={spec.format}")

            # Create ROI for resize/resample (xbegin, xend, ybegin, yend, zbegin, zend, chbegin, chend)
            roi = oiio_module.ROI(0, target_size[0], 0, target_size[1], 0, 1, 0, input_buf.nchannels)

            # Use resample for ID passes (no interpolation), resize for others
            if not interpolate:
                # ID passes: use resample (no interpolation) to preserve discrete values
                resized_buf = oiio_module.ImageBufAlgo.resample(input_buf, roi=roi, interpolate=False)
                print(f"[DEBUG RESIZE] Resampled to {target_size[0]}x{target_size[1]} (no interpolation)")
            else:
                # Beauty/lighting passes: use resize with interpolation filter
                resized_buf = oiio_module.ImageBufAlgo.resize(input_buf, filtername=interpolation, roi=roi)
                print(f"[DEBUG RESIZE] Resized to {target_size[0]}x{target_size[1]} using filter: {interpolation}")

            # Force EXR windows to match
            outspec = resized_buf.specmod()
            outspec.x = 0
            outspec.y = 0
            outspec.width = target_size[0]
            outspec.height = target_size[1]
            outspec.full_x = 0
            outspec.full_y = 0
            outspec.full_width = target_size[0]
            outspec.full_height = target_size[1]
            print(f"[DEBUG RESIZE] Forced EXR windows to match")

            # Write output
            write_success = resized_buf.write(target_path)

            if not write_success:
                # Get error with API compatibility - geterror is always a method
                write_err = resized_buf.geterror()
                return False, f"Failed to write image: {write_err}"

            print(f"[DEBUG RESIZE] Successfully saved to: {target_path}")
            return True, None

        except Exception as e:
            print(f"[DEBUG RESIZE] ERROR: {e}")
            import traceback
            print(f"[DEBUG RESIZE] Traceback: {traceback.format_exc()}")
            return False, str(e)

    @err_catcher(name=__name__)
    def batchResizeAOV(self, files, target_size, interpolation, interpolate,
                       backup_folder, progress_callback=None):
        """
        Resize all files in an AOV folder.

        Strategy:
        1. Create backup of each original file
        2. Read from SOURCE directly (avoid network-sync issues with backup copy)
        3. Resize and write to source in-place
        4. If resize fails, restore from backup

        Args:
            files: List of file paths to resize
            target_size: Tuple of (width, height)
            interpolation: OpenImageIO filter string (for when interpolate=True)
            interpolate: If False, use nearest-neighbor resample
            backup_folder: Path to backup folder
            progress_callback: Optional callback(current, total) for progress updates

        Returns dict with success/failure counts and errors.
        """
        results = {
            'total': len(files),
            'success': 0,
            'failed': 0,
            'errors': []
        }

        # Ensure backup folder exists
        backup_folder = os.path.normpath(backup_folder)
        try:
            os.makedirs(backup_folder, exist_ok=True)
            print(f"[DEBUG] Backup folder ready: {backup_folder}")
        except Exception as e:
            print(f"[DEBUG] Failed to create backup folder: {e}")
            results['errors'].append(f"Failed to create backup folder: {e}")
            return results

        for i, source_path in enumerate(files):
            filename = os.path.basename(source_path)
            source_path = os.path.normpath(source_path)
            backup_path = os.path.normpath(os.path.join(backup_folder, filename))

            try:
                # Step 1: Create backup copy first
                print(f"[DEBUG] Backing up: {filename}")
                shutil.copy2(source_path, backup_path)

                # Verify backup was created
                if not os.path.exists(backup_path):
                    raise Exception(f"Backup file not created: {backup_path}")

                backup_size = os.path.getsize(backup_path)
                source_size = os.path.getsize(source_path)
                print(f"[DEBUG] Backup created: {backup_size} bytes (source: {source_size} bytes)")

                # Step 2: Read from SOURCE directly and resize to source location
                # This avoids network synchronization issues with reading from backup
                print(f"[DEBUG] Resizing from source: {source_path}")
                success, error = self.resizeImage(
                    source_path, source_path, target_size,
                    interpolation, interpolate
                )

                if success:
                    results['success'] += 1
                    print(f"[DEBUG] Successfully resized: {filename}")
                else:
                    # Step 3: On failure, restore from backup
                    print(f"[DEBUG] Resize failed, restoring from backup: {error}")
                    try:
                        shutil.copy2(backup_path, source_path)
                        print(f"[DEBUG] Restored: {filename}")
                    except Exception as restore_err:
                        print(f"[DEBUG] Failed to restore: {restore_err}")
                    results['failed'] += 1
                    results['errors'].append(f"{filename}: {error}")

            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"{filename}: {str(e)}")
                print(f"[DEBUG] Exception processing {filename}: {e}")
                import traceback
                print(f"[DEBUG] Traceback: {traceback.format_exc()}")

            # Progress callback
            if progress_callback:
                progress_callback(i + 1, len(files))

        return results

    @err_catcher(name=__name__)
    def isOIIOAvailable(self):
        """Check if OpenImageIO library is available."""
        return OIIO_AVAILABLE

    @err_catcher(name=__name__)
    def hasEXRSupport(self):
        """Check if EXR format is supported via OpenImageIO."""
        return OIIO_AVAILABLE

    @err_catcher(name=__name__)
    def getMissingPackages(self):
        """Return list of missing packages for EXR resize support."""
        missing = []
        if not OIIO_AVAILABLE:
            missing.append('OpenImageIO')  # Official package name on PyPI
        return missing

    @err_catcher(name=__name__)
    def debugPackageStatus(self):
        """Print debug info about package availability and paths."""
        import sys
        print("[DEBUG OIIO] === Package Status Check ===")
        print(f"[DEBUG OIIO] OIIO_AVAILABLE: {OIIO_AVAILABLE}")

        # Check sys.path
        print(f"[DEBUG OIIO] sys.path entries ({len(sys.path)}):")
        for i, p in enumerate(sys.path[:10]):  # Show first 10
            print(f"[DEBUG OIIO]   [{i}] {p}")

        # Check local lib directories
        current_dir = os.path.dirname(os.path.abspath(__file__))
        aftereffects_dir = os.path.dirname(os.path.dirname(current_dir))
        possible_libs = [
            os.path.join(aftereffects_dir, "lib", "python311", "site-packages"),
            os.path.join(aftereffects_dir, "lib", "python39", "site-packages"),
        ]

        print(f"[DEBUG OIIO] AfterEffects dir: {aftereffects_dir}")
        print(f"[DEBUG OIIO] Local lib directories:")
        for lib in possible_libs:
            exists = os.path.exists(lib)
            in_path = lib in sys.path

            # Check for both possible folder names
            oiio_folder = os.path.join(lib, "OpenImageIO")
            oiio_folder2 = os.path.join(lib, "oiio")

            oiio_exists = os.path.exists(oiio_folder) if exists else False
            oiio2_exists = os.path.exists(oiio_folder2) if exists else False

            print(f"[DEBUG OIIO]   {lib}")
            print(f"[DEBUG OIIO]     exists={exists}, in sys.path={in_path}")
            print(f"[DEBUG OIIO]     OpenImageIO folder exists={oiio_exists}")
            print(f"[DEBUG OIIO]     oiio folder exists={oiio2_exists}")

            # Check what folders exist
            if exists:
                try:
                    folders = [d for d in os.listdir(lib) if not d.startswith('.')]
                    print(f"[DEBUG OIIO]     folders: {folders[:15]}")  # Show first 15
                except Exception as e:
                    print(f"[DEBUG OIIO]     Cannot list: {e}")

        # Try importing OpenImageIO now
        print("[DEBUG OIIO] Attempting to import OpenImageIO...")
        try:
            import OpenImageIO as oiio_test
            print(f"[DEBUG OIIO] SUCCESS: OpenImageIO imported!")
            print(f"[DEBUG OIIO] Version: {oiio_test.__version__ if hasattr(oiio_test, '__version__') else 'unknown'}")
        except ImportError as e:
            print(f"[DEBUG OIIO] FAILED: {e}")
            # Try alternative import
            print("[DEBUG OIIO] Attempting alternative import: oiio...")
            try:
                import oiio as oiio_test2
                print(f"[DEBUG OIIO] SUCCESS: oiio imported!")
                oiio2_ver = oiio_test2.__version__ if hasattr(oiio_test2, '__version__') else 'unknown'
                print(f"[DEBUG OIIO] Version: {oiio2_ver}")
            except ImportError as e2:
                print(f"[DEBUG OIIO] FAILED: {e2}")
        except Exception as e:
            print(f"[DEBUG OIIO] ERROR: {e}")

        print("[DEBUG OIIO] === End Package Status ===")
