#!/usr/bin/env python3
"""
豆瓣数据JSON导出命令行工具
"""
import os
import sys
import argparse
from pathlib import Path

# 添加父目录到路径
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.append(str(project_root))

# 导入导出服务
from services.export.json_exporter import JsonExporter
from services.data.database import Database
from utils.logger import get_logger

logger = get_logger("export_cli")

def main():
    """命令行入口函数"""
    parser = argparse.ArgumentParser(description="豆瓣数据JSON导出工具")
    parser.add_argument('--type', '-t', help="内容类型 (movie, tv, book, music, game, drama)")
    parser.add_argument('--status', '-s', help="状态 (wish, doing, done)")
    parser.add_argument('--year', '-y', type=int, help="年份筛选")
    parser.add_argument('--output', '-o', help="输出文件路径")
    parser.add_argument('--db', help="SQLite数据库路径")
    parser.add_argument('--raw', action='store_true', help="包含原始JSON数据")
    parser.add_argument('--compact', action='store_true', help="输出紧凑JSON格式")
    parser.add_argument('--all', '-a', action='store_true', help="导出所有类型和状态（多文件）")
    parser.add_argument('--limit', '-l', type=int, help="最大导出条目数")
    
    args = parser.parse_args()
    
    try:
        # 初始化数据库
        db = Database(args.db) if args.db else Database()
        
        # 初始化导出器
        exporter = JsonExporter(db)
        
        if args.all:
            # 导出所有类型和状态到多个文件
            output_dir = args.output if args.output else None
            result_dir = exporter.export_all_types(output_dir, args.raw)
            print(f"\n导出成功! 所有文件保存在: {result_dir}\n")
        else:
            # 导出单个查询结果
            output_path = exporter.export_data(
                type_=args.type,
                status=args.status,
                year=args.year,
                output_path=args.output,
                include_raw=args.raw,
                pretty_print=not args.compact,
                limit=args.limit
            )
            
            if output_path:
                print(f"\n导出成功! 文件路径: {output_path}\n")
            else:
                print("\n没有找到匹配的数据\n")
                return 1
        
    except Exception as e:
        logger.error(f"导出失败: {e}", exc_info=True)
        print(f"\n导出失败: {e}\n")
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())