import importlib
import pkgutil


def _iter_command_modules():
    for m in pkgutil.iter_modules(__path__):
        name = getattr(m, "name", "")
        if not name or name.startswith("_"):
            continue
        if name == "__init__":
            continue
        yield name


def _collect_mixins():
    out = {}
    for mod_name in _iter_command_modules():
        mod = importlib.import_module(f"{__name__}.{mod_name}")
        for k, v in (mod.__dict__ or {}).items():
            if not k.endswith("CommandsMixin"):
                continue
            if not isinstance(v, type):
                continue
            out[k] = v
    return out


_MIXINS = _collect_mixins()
globals().update(_MIXINS)

__all__ = sorted(_MIXINS.keys())
