# 專案完整架構探測報告 (Plan6)

**最後更新: 2025-09-22 11:40**

## 一、 完整檔案樹狀結構圖

```
.
├── .gitignore
├── AGENTS.md
├── Log.md
├── Plan3.md
├── Plan4.md
├── Plan5.md
├── Plan6.md
├── TOOLS_README.md
├── cleanup_report_20250917.md
├── colabPro.py
├── config
│   ├── circus.ini.template
│   └── config.json.template
├── pyproject.toml
├── pytest.ini
├── requirements
│   ├── analysis.txt
│   ├── core.txt
│   ├── downloader.txt
│   ├── features_core.txt
│   ├── features_non_core.txt
│   ├── gemini.txt
│   ├── test.txt
│   └── transcriber.txt
├── scripts
│   ├── check_deps.py
│   ├── colab_key_injector.py
│   ├── migrate_keys_to_db.py
│   ├── quantitative_analysis_poc.py
│   ├── run_processing_pipeline.py
│   └── time.py
├── services
│   ├── bond_data_service
│   │   ├── bond_data.sqlite3
│   │   ├── data_fetchers
│   │   │   ├── fred_cpi_fetcher.py
│   │   │   ├── fred_fedfunds_fetcher.py
│   │   │   ├── fred_gdp_fetcher.py
│   │   │   └── fred_ism_fetcher.py
│   │   ├── data_manager.py
│   │   ├── database.py
│   │   ├── main.py
│   │   └── requirements.txt
│   └── key_service
│       ├── main.py
│       └── requirements.txt
├── src
│   ├── api
│   │   ├── __init__.py
│   │   ├── api_server.py
│   │   ├── dependencies.py
│   │   └── routes
│   │       ├── __init__.py
│   │       ├── bond_service_proxy.py
│   │       ├── page1.py
│   │       ├── page10_test.py
│   │       ├── page2_downloader.py
│   │       ├── page3_processor.py
│   │       ├── page4_analyzer.py
│   │       ├── page5_backup.py
│   │       ├── page6_keys.py
│   │       ├── page7_prompts.py
│   │       ├── page8_details.py
│   │       ├── page9_dashboard.py
│   │       ├── system.py
│   │       └── ui.py
│   ├── core
│   │   ├── __init__.py
│   │   ├── config_manager.py
│   │   ├── filename_utils.py
│   │   ├── key_manager.py
│   │   ├── orchestrator.py
│   │   ├── prompt_manager.py
│   │   ├── rendering.py
│   │   └── time_utils.py
│   ├── db
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── database.py
│   │   ├── database.sqlite3
│   │   ├── initialize_database.py
│   │   ├── log_handler.py
│   │   └── manager.py
│   ├── prompts
│   │   └── default_prompts.json
│   ├── static
│   │   ├── _processed_file_item.html
│   │   ├── css
│   │   │   ├── common.css
│   │   │   ├── main.css
│   │   │   ├── nav.css
│   │   │   ├── page1.css
│   │   │   ├── page1_unified.css
│   │   │   ├── page2.css
│   │   │   ├── page3.css
│   │   │   ├── page4.css
│   │   │   ├── page4_summary.css
│   │   │   ├── page5.css
│   │   │   ├── page6.css
│   │   │   ├── page7.css
│   │   │   ├── page8.css
│   │   │   └── page9.css
│   │   ├── export_cards.html
│   │   ├── export_table.html
│   │   ├── history.html
│   │   ├── js
│   │   │   └── page_bond.js
│   │   ├── json_viewer.html
│   │   ├── line_extractor.html
│   │   ├── main.html
│   │   ├── mp3.html
│   │   ├── page1.html
│   │   ├── page10_service_test.html
│   │   ├── page1_sub_export.html
│   │   ├── page1_sub_ingestion.html
│   │   ├── page1_sub_overview.html
│   │   ├── page2_downloader.html
│   │   ├── page3_processor.html
│   │   ├── page4_stage1_5_date.html
│   │   ├── page4_stage1_ai.html
│   │   ├── page4_stage2_performance.html
│   │   ├── page4_stage3_report.html
│   │   ├── page4_stage4_download.html
│   │   ├── page4_summary_center.html
│   │   ├── page5_backup.html
│   │   ├── page6_keys.html
│   │   ├── page7_prompts.html
│   │   ├── page8_file_details.html
│   │   ├── page9_dashboard.html
│   │   ├── page_bond.html
│   │   ├── prompts.html
│   │   └── report_viewer.html
│   └── tools
│       ├── __init__.py
│       ├── content_extractor.py
│       ├── document_analyzer.py
│       ├── drive_downloader.py
│       ├── file_hasher.py
│       ├── gdrive_backup.py
│       ├── gemini_manager.py
│       ├── gemini_processor.py
│       ├── image_compressor.py
│       ├── mock_downloader_for_test.py
│       ├── mock_gemini_processor.py
│       ├── mock_transcriber.py
│       ├── mock_youtube_downloader.py
│       ├── pdf_parser.py
│       ├── quantitative_analyzer.py
│       ├── readme_tool.py
│       ├── report_generator.py
│       ├── report_generator_docx.py
│       ├── taiwan_stock_suffix_helper.py
│       ├── transcriber.py
│       ├── universal_downloader.py
│       ├── url_extractor.py
│       └── youtube_downloader.py
├── tests
│   ├── .gitkeep
│   ├── conftest.py
│   ├── test_bond_chart_generation.py
│   ├── test_bond_service_startup.py
│   ├── test_page4_summary_and_models.py
│   └── test_summary_page_e2e.py
└── 一級交易pro.py
```
