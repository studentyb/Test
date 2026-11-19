# from debug.java_debugger import run_java_line_tracer
#
# # 获取第一个失败的 assertion error 测试用例
#
# [G]   project_path: D:\BJFU\TestAgent\crewAI\pro-mas-crewai\src\pro_mas_crewai\output\project_code\login\backend\src\main\java
# [G]   class_name: user_authentication.service.impl.AuthenticationServiceImpl
# [G]   method_name: findUserIdentityByUsername
# [G]   test_method: user_authentication.service.impl.AuthenticationServiceImplTest#test_tc_002_empty_username_returns_null_useridentity
# [G]   jar_path: D:\BJFU\TestAgent\project\TestAgent\debug\line-tracer.jar
#
#
#     # test_method: 完整的测试方法名，如 "com.example.TestClass#testMethod"
#     test_method = f"{failed_tc.class_name}#{failed_tc.test_name}"
#
#     # 打印参数用于调试对比
#     print(f"[G] Line tracer params:")
#     print(f"[G]   project_path: {str(self.sut_root)}")
#     print(f"[G]   class_name: {sut_class_name}")
#     print(f"[G]   method_name: {sut_method_name}")
#     print(f"[G]   test_method: {test_method}")
#     print(f"[G]   jar_path: {jar_path}")
#
#     returncode, stdout, stderr = run_java_line_tracer(
#         project_path=str(self.sut_root),
#         class_name=sut_class_name,
#         method_name=sut_method_name,
#         test_method=test_method,
#         jar_path=jar_path,  # 使用绝对路径
#         timeout=30  # 设置超时时间为 120 秒，等待 Maven 编译和 JVM 启动
#     )
#
#     if returncode == 0:
#         line_tracer_info = stdout
#         log.info(f"[G] Line tracer output retrieved: {len(stdout)} chars")
#     else:
#         log.warning(f"[G] Line tracer failed: {stderr}")
