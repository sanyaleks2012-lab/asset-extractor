import argparse
import json
import os
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import UnityPy
from UnityPy.classes import (
    Font,
    GameObject,
    Mesh,
    MonoBehaviour,
    Object,
    PPtr,
    Shader,
    Sprite,
    TextAsset,
    Texture2D,
)
from UnityPy.enums.ClassIDType import ClassIDType
from UnityPy.files import ObjectReader, SerializedFile


def export_obj(
    obj: Union[ObjectReader, PPtr],
    fp: str,
    append_name: bool = False,
    append_path_id: bool = False,
    export_unknown_as_typetree: bool = False,
    asset_filter: Optional[Callable[[Object], bool]] = None,
) -> List[Tuple[SerializedFile, int]]:
    export_func = EXPORT_TYPES.get(obj.type)
    if not export_func:
        if export_unknown_as_typetree:
            export_func = exportMonoBehaviour
        else:
            return []

    if isinstance(obj, PPtr):
        obj = obj.deref()

    instance = obj.parse_as_object()

    if asset_filter and not asset_filter(instance):
        return []

    if append_name:
        name = getattr(instance, "m_Name", obj.type.name)
        fp = os.path.join(fp, name)

    if append_path_id:
        fp = f"{fp}_{obj.m_PathID}"

    return export_func(instance, fp)


def extract_assets(
    src: Union[Path, str],
    dst: Path,
    use_container: bool = True,
    ignore_first_container_dirs: int = 0,
    append_path_id: bool = False,
    export_unknown_as_typetree: bool = False,
    asset_filter: Optional[Callable[[Object], bool]] = None,
) -> List[Tuple[SerializedFile, int]]:
    env = UnityPy.load(str(src) if isinstance(src, Path) else src)
    exported = []

    export_types_keys = list(EXPORT_TYPES.keys())

    def defaulted_export_index(type: ClassIDType):
        try:
            return export_types_keys.index(type)
        except (IndexError, ValueError):
            return 999

    if use_container:
        container = sorted(env.container.items(), key=lambda x: defaulted_export_index(x[1].type))
        for obj_path, obj in container:
            if asset_filter is not None and not asset_filter(obj):
                continue
            obj_dest = os.path.join(
                dst,
                *(x for x in obj_path.split("/")[ignore_first_container_dirs:] if x),
            )
            os.makedirs(os.path.dirname(obj_dest), exist_ok=True)
            exported.extend(
                export_obj(
                    obj,
                    obj_dest,
                    append_path_id=append_path_id,
                    export_unknown_as_typetree=export_unknown_as_typetree,
                    asset_filter=asset_filter,
                )
            )
    else:
        objects = sorted(env.objects, key=lambda x: defaulted_export_index(x.type))
        for obj in objects:
            if asset_filter is not None and not asset_filter(obj):
                continue
            if (obj.assets_file, obj.path_id) not in exported:
                exported.extend(
                    export_obj(
                        obj,
                        str(dst),
                        append_name=True,
                        append_path_id=append_path_id,
                        export_unknown_as_typetree=export_unknown_as_typetree,
                        asset_filter=asset_filter,
                    )
                )

    return exported


def exportTextAsset(
    obj: Union[TextAsset, ObjectReader], fp: str, extension: str = ".txt"
) -> List[Tuple[SerializedFile, int]]:
    if isinstance(obj, ObjectReader):
        obj = obj.parse_as_object()
    out_path = fp if os.path.splitext(fp)[1] else f"{fp}{extension}"
    with open(out_path, "wb") as f:
        f.write(obj.m_Script.encode("utf-8", "surrogateescape"))
    return [(obj.assets_file, obj.object_reader.path_id)]


def exportFont(obj: Union[Font, ObjectReader], fp: str) -> List[Tuple[SerializedFile, int]]:
    if isinstance(obj, ObjectReader):
        obj = obj.parse_as_object()
    if obj.m_FontData:
        ext = ".ttf"
        if obj.m_FontData[0:4] == b"OTTO":
            ext = ".otf"
        out_path = fp if os.path.splitext(fp)[1] else f"{fp}{ext}"
        with open(out_path, "wb") as f:
            f.write(bytes(obj.m_FontData))
    return [(obj.assets_file, obj.object_reader.path_id)]


def exportMesh(obj: Union[Mesh, ObjectReader], fp: str, extension: str = ".obj") -> List[Tuple[SerializedFile, int]]:
    if isinstance(obj, ObjectReader):
        obj = obj.parse_as_object()
    out_path = fp if os.path.splitext(fp)[1] else f"{fp}{extension}"
    with open(out_path, "wt", encoding="utf8", newline="") as f:
        f.write(obj.export())
    return [(obj.assets_file, obj.object_reader.path_id)]


def exportShader(obj: Union[Shader, ObjectReader], fp: str, extension: str = ".txt") -> List[Tuple[SerializedFile, int]]:
    if isinstance(obj, ObjectReader):
        obj = obj.parse_as_object()
    out_path = fp if os.path.splitext(fp)[1] else f"{fp}{extension}"
    with open(out_path, "wt", encoding="utf8", newline="") as f:
        f.write(obj.export())
    return [(obj.assets_file, obj.object_reader.path_id)]


def exportMonoBehaviour(
    obj: Union[MonoBehaviour, ObjectReader], fp: str
) -> List[Tuple[SerializedFile, int]]:
    reader = obj.object_reader if isinstance(obj, MonoBehaviour) else obj

    try:
        export = reader.parse_as_dict()
        ext = ".json"
        export_bytes = json.dumps(export, indent=4, ensure_ascii=False).encode("utf8", errors="surrogateescape")
    except Exception:
        ext = ".bin"
        export_bytes = reader.get_raw_data()

    out_path = fp if os.path.splitext(fp)[1] else f"{fp}{ext}"
    with open(out_path, "wb") as f:
        f.write(export_bytes)
    return [(obj.assets_file, obj.path_id)]


def exportSprite(
    obj: Union[Sprite, ObjectReader], fp: str, extension: str = ".png"
) -> List[Tuple[SerializedFile, int]]:
    if isinstance(obj, ObjectReader):
        sprite = obj.parse_as_object()
    else:
        sprite = obj
        obj = sprite.object_reader

    out_path = fp if os.path.splitext(fp)[1] else f"{fp}{extension}"
    sprite.image.save(out_path)
    
    exported = [
        (obj.assets_file, obj.path_id),
        (sprite.m_RD.texture.assetsfile, sprite.m_RD.texture.path_id),
    ]
    alpha_assets_file = getattr(sprite.m_RD.alphaTexture, "assets_file", None)
    alpha_path_id = getattr(sprite.m_RD.alphaTexture, "path_id", None)
    if alpha_path_id and alpha_assets_file:
        exported.append((alpha_assets_file, alpha_path_id))
    return exported


def exportTexture2D(
    obj: Union[Texture2D, ObjectReader], fp: str, extension: str = ".png"
) -> List[Tuple[SerializedFile, int]]:
    if isinstance(obj, ObjectReader):
        obj = obj.parse_as_object()
    if obj.m_Width:
        out_path = fp if os.path.splitext(fp)[1] else f"{fp}{extension}"
        obj.image.save(out_path)
    return [(obj.assets_file, obj.object_reader.path_id)]


def exportGameObject(
    obj: Union[GameObject, ObjectReader], fp: str
) -> List[Tuple[SerializedFile, int]]:
    if isinstance(obj, ObjectReader):
        obj = obj.parse_as_object()
    exported = [(obj.assets_file, obj.object_reader.path_id)]
    refs = crawl_obj(obj)
    if refs:
        os.makedirs(fp, exist_ok=True)
    for ref_id, ref in refs.items():
        if (ref.assets_file, ref_id) in exported or ref.type == ClassIDType.GameObject:
            continue
        try:
            exported.extend(export_obj(ref, fp, True, True))
        except Exception as e:
            print(f"Failed to export {ref_id}: {e}")
    return exported


EXPORT_TYPES = {
    ClassIDType.GameObject: exportGameObject,
    ClassIDType.Sprite: exportSprite,
    ClassIDType.Font: exportFont,
    ClassIDType.Mesh: exportMesh,
    ClassIDType.MonoBehaviour: exportMonoBehaviour,
    ClassIDType.Shader: exportShader,
    ClassIDType.TextAsset: exportTextAsset,
    ClassIDType.Texture2D: exportTexture2D,
}


def crawl_obj(obj: Union[Object, ObjectReader, PPtr], ret: Optional[dict] = None) -> Dict[int, Union[Object, PPtr]]:
    if not ret:
        ret = {}

    if isinstance(obj, PPtr):
        if obj.m_PathID == 0 and obj.m_FileID == 0 and obj.m_Index == -2:
            return ret
        try:
            instance = obj.deref_parse_as_dict()
            values = instance.values()
        except AttributeError:
            return ret
    elif isinstance(obj, Object):
        values = obj.__dict__.values()
    elif isinstance(obj, ObjectReader):
        values = obj.parse_as_dict().values()
    else:
        return ret

    ret[obj.m_PathID] = obj

    for value in flatten(values):
        if isinstance(value, (Object, PPtr)):
            if value.m_PathID in ret:
                continue
            crawl_obj(value, ret)

    return ret


def flatten(seq: Sequence) -> Iterable:
    for elem in list(seq):
        if isinstance(elem, (list, tuple)):
            yield from flatten(elem)
        elif isinstance(elem, dict):
            yield from flatten(elem.values())
        else:
            yield elem


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unity Assets Exporter CLI")
    parser.add_argument("src", type=str, help="Path to input Unity asset/bundle file or folder")
    parser.add_argument("dst", type=str, help="Path to output destination directory")
    parser.add_argument(
        "--no-container",
        action="store_false",
        dest="use_container",
        help="Disable using container paths",
    )
    parser.add_argument(
        "--append-path-id",
        action="store_true",
        help="Append path_id to filenames",
    )
    parser.add_argument(
        "--export-unknown",
        action="store_true",
        dest="export_unknown_as_typetree",
        help="Export unknown objects as typetree/bin",
    )

    args = parser.parse_args()

    src_path = Path(args.src)
    dst_path = Path(args.dst)

    if not src_path.exists():
        print(f"Error: Source path '{src_path}' does not exist.")
        exit(1)

    os.makedirs(dst_path, exist_ok=True)

    # Собираем список файлов для обработки
    files_to_process = []
    if src_path.is_file():
        files_to_process.append(src_path)
    else:
        for root, _, files in os.walk(src_path):
            for file in files:
                files_to_process.append(Path(root) / file)

    print(f"Found {len(files_to_process)} files to process in: {src_path}")
    print(f"Destination directory: {dst_path}")

    total_exported = 0
    for file_path in files_to_process:
        try:
            exported_items = extract_assets(
                src=str(file_path),
                dst=dst_path,
                use_container=args.use_container,
                append_path_id=args.append_path_id,
                export_unknown_as_typetree=args.export_unknown_as_typetree,
            )
            total_exported += len(exported_items)
        except Exception as e:
            # Игнорируем файлы, которые не являются Unity-бандлами
            print(f"Skipping {file_path.name}: {e}")

    print(f"Done! Successfully exported {total_exported} items in total.")
