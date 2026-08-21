import os
import sys
import time
import shutil

def atomic_cross_drive_commit(temp_source_path: str, final_target_path: str, max_retries: int = 5) -> bool:
    """
    Risolve i problemi di WinError 5 (lock Google Drive) e WinError 17 (move cross-drive C: -> G:)
    1. Copia la patch approvata in una directory temporanea .staging/ sul DRIVE DI DESTINAZIONE (G:)
    2. Esegue un os.replace atomico protetto da Win32 Exponential Backoff.
    """
    try:
        target_dir = os.path.dirname(final_target_path)
        staging_dir = os.path.join(target_dir, ".staging")
        os.makedirs(staging_dir, exist_ok=True)
        
        file_name = os.path.basename(final_target_path)
        staged_file_path = os.path.join(staging_dir, f"{file_name}.staged")
        
        # 1. Copia da %TEMP% (C:) a .staging/ (G:)
        shutil.copy2(temp_source_path, staged_file_path)
        
        # 2. Atomic replace con Exponential Backoff su Windows
        backoff_sec = 0.1
        replaced_success = False
        for attempt in range(max_retries):
            try:
                os.replace(staged_file_path, final_target_path)
                replaced_success = True
                break
            except PermissionError as pe:
                if attempt == max_retries - 1:
                    raise pe
                time.sleep(backoff_sec)
                backoff_sec *= 2.0
            except OSError as oe:
                if getattr(oe, 'winerror', None) in (5, 32): # Lock o Access Denied
                    if attempt == max_retries - 1:
                        raise oe
                    time.sleep(backoff_sec)
                    backoff_sec *= 2.0
                else:
                    raise oe

        # Cleanup if staging directory is local and empty
        try:
            if not replaced_success and os.path.exists(staged_file_path):
                os.remove(staged_file_path)
            if os.path.exists(staging_dir) and not os.listdir(staging_dir):
                os.rmdir(staging_dir)
        except Exception:
            pass

        return replaced_success
    except Exception as e:
        print(f"[CrossDriveStager Error] {str(e)}")
        return False

if __name__ == "__main__":
    print("[NK-Oracle-Evaluator] Cross-Drive Stager Engine Ready.")
