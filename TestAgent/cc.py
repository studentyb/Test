from pathlib import Path

from generation.agent_with_ca import Test4CA



# if __name__ == '__main__':
#     root=Path('D:\BJFU\TestAgent\dataset\RQ4\workdir\Actor_relationship_game')
#     app = Test4CA(
#         build='gradle',
#         sut_root=root/'src/main/java',
#         dataset_root=root,
#         put='',
#         language='java',
#         feature='',
#         verbose=False,
#         debug=False,
#         stream=not args.no_stream,
#         exp=False,
#         max_retries=1,
#         # todo
#         uml_class=''
#     )
#     app.run()
#
#     if args.report_path:
#         report_path = Path(args.report_path)
#         source_path = Path(f"memory/working_memory/debug_report_{args.feature}.json")
#         if source_path.exists():
#             report_path.parent.mkdir(parents=True, exist_ok=True)
#             shutil.copy2(source_path, report_path)
#         else:
#             print(f"Warning: Source file {source_path} does not exist")
#
#
#
#     )