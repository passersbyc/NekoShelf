from abc import ABC, abstractmethod
from typing import Tuple, Optional

class DownloadPlugin(ABC):
    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Return True if this plugin can handle the given URL."""
        pass

    @abstractmethod
    def download(self, url: str, output_dir: str, **kwargs) -> Tuple[bool, str, Optional[str]]:
        """
        下载资源
        
        Args:
            url: 目标URL
            output_dir: 输出目录
            **kwargs: 额外参数 (如 db 实例)
            
        Returns:
            (success, message, output_path)
        """
        raise NotImplementedError
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of the plugin."""
        pass

    def get_artist_name(self, url: str) -> str:
        """
        Get artist name from URL.
        Optional implementation.
        """
        return ""
