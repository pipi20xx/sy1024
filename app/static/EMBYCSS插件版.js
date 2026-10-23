// ==UserScript==
// @name         神医TMDB网页增强工具 (通用版)
// @namespace    http://tampermonkey.net/
// @version      5.3
// @description  在 Emby 页面添加四个快捷按钮，使用美化的Toast通知和自定义确认对话框。已适配普通JS环境。
// @author       Gemini (UI美化版)
// @match        *://*/web/index.html*
// @license MIT
// @run-at       document-end
// ==/UserScript==

(function() {
    'use strict';

    // ===============================================
    // ==          【请在这里统一配置】             ==
    // ===============================================
    // 注意：如果在非油猴环境使用，请确保此 Webhook 地址允许跨域 (CORS) 请求
    const WEBHOOK_URL = 'http://192.168.50.252:8121/api/webhook/emby/925789834a7b972d90df41b495b32c9ce104d2c0edbe69d7';
    
    // 是否启用存储信息查询功能
    const ENABLE_STORAGE_INFO = true;
    
    // 存储信息面板默认状态：true=展开，false=折叠
    const STORAGE_PANEL_DEFAULT_EXPANDED = true;
    
    // 发送的数据结构模板
    const WEBHOOK_DATA_STRUCTURE = {
      "Server": { "Name": "JS Script" },
      "User": { "Name": "Manual Trigger" },
      "Event": "{{event_name}}", 
      "Item": {
        "Id": "{{itemId}}",
        "Type": "{{itemType}}",
        "Name": "{{itemName}}",
        "ProviderIds": {
          "Tmdb": "{{tmdbId}}",
          "Imdb": "{{imdbId}}",
          "Tvdb": "{{tvdbId}}"
        }
      }
    };
    // ===============================================


    // --- UI组件区：美化的通知和确认框 ---

    /**
     * 显示一个会自动消失的 Toast 通知
     */
    function showToastNotification(message, type = 'success') {
        const toastId = 'emby-toolkit-toast';
        document.getElementById(toastId)?.remove();
        const toast = document.createElement('div');
        toast.id = toastId;
        toast.innerHTML = message;
        Object.assign(toast.style, {
            position: 'fixed',
            top: '20px',
            right: '-350px',
            padding: '15px 20px',
            borderRadius: '8px',
            backgroundColor: type === 'success' ? '#4CAF50' : '#F44336',
            color: 'white',
            zIndex: '20000',
            fontSize: '16px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
            transition: 'right 0.5s ease-in-out',
            opacity: '1',
            maxWidth: '320px',
            wordBreak: 'break-word'
        });
        document.body.appendChild(toast);
        setTimeout(() => {
            toast.style.right = '20px';
        }, 100);
        setTimeout(() => {
            toast.style.right = '-350px';
            setTimeout(() => {
                toast.remove();
            }, 500);
        }, 4000);
    }

    /**
     * 显示自定义确认对话框
     */
    function showCustomConfirm(message, confirmText = '确定', confirmColor = '#F44336') {
        return new Promise(resolve => {
            const confirmId = 'emby-toolkit-confirm-modal';
            document.getElementById(confirmId)?.remove();

            const overlay = document.createElement('div');
            overlay.id = confirmId;
            Object.assign(overlay.style, {
                position: 'fixed', top: '0', left: '0', width: '100vw', height: '100vh',
                backgroundColor: 'rgba(0, 0, 0, 0.6)', zIndex: '19999', display: 'flex',
                justifyContent: 'center', alignItems: 'center', opacity: '0',
                transition: 'opacity 0.2s ease-in-out'
            });

            const modal = document.createElement('div');
            Object.assign(modal.style, {
                backgroundColor: 'white', padding: '24px', borderRadius: '12px',
                boxShadow: '0 8px 30px rgba(0,0,0,0.2)', textAlign: 'center',
                maxWidth: '90%', width: '420px', transform: 'scale(0.95)',
                transition: 'transform 0.2s ease-in-out'
            });

            const msgElement = document.createElement('p');
            msgElement.innerHTML = message.replace(/\n/g, '<br>');
            Object.assign(msgElement.style, {
                color: '#333', fontSize: '16px', margin: '0 0 24px 0', lineHeight: '1.6', textAlign: 'left'
            });

            const btnContainer = document.createElement('div');
            Object.assign(btnContainer.style, { display: 'flex', justifyContent: 'flex-end', gap: '12px' });

            const confirmBtn = document.createElement('button');
            confirmBtn.textContent = confirmText;
            const cancelBtn = document.createElement('button');
            cancelBtn.textContent = '取消';

            const baseBtnStyle = {
                padding: '10px 20px', border: 'none', borderRadius: '6px',
                fontSize: '15px', cursor: 'pointer', transition: 'all 0.2s', fontWeight: 'bold'
            };
            Object.assign(confirmBtn.style, baseBtnStyle, { backgroundColor: confirmColor, color: 'white' });
            Object.assign(cancelBtn.style, baseBtnStyle, { backgroundColor: '#e9ecef', color: '#555' });

            [confirmBtn, cancelBtn].forEach(btn => {
                btn.onmouseover = () => btn.style.filter = 'brightness(0.9)';
                btn.onmouseout = () => btn.style.filter = 'brightness(1)';
            });

            btnContainer.appendChild(cancelBtn);
            btnContainer.appendChild(confirmBtn);
            modal.appendChild(msgElement);
            modal.appendChild(btnContainer);
            overlay.appendChild(modal);
            document.body.appendChild(overlay);

            setTimeout(() => { overlay.style.opacity = '1'; modal.style.transform = 'scale(1)'; }, 10);

            const cleanup = (result) => {
                overlay.style.opacity = '0';
                modal.style.transform = 'scale(0.95)';
                setTimeout(() => { overlay.remove(); }, 200);
                resolve(result);
            };

            confirmBtn.onclick = () => cleanup(true);
            cancelBtn.onclick = () => cleanup(false);
            overlay.onclick = (e) => { if (e.target === overlay) { cleanup(false); } };
        });
    }

    // --- 通用工具函数 ---
    function getApiClient() {
        if (typeof ApiClient !== 'undefined') return ApiClient;
        if (typeof window.ApiClient !== 'undefined') return window.ApiClient;
        return null;
    }

    function extractItemIdFromUrl() {
        try {
            return /id=([^&]+)/.exec(window.location.hash)?.[1] || null;
        } catch (e) { return null; }
    }

    // --- 核心功能：获取信息并发送 Webhook ---
    async function getMediaItemFromApi(itemId) {
        const apiClient = getApiClient();
        if (!apiClient) return null;
        try {
            const userId = apiClient.getCurrentUserId ? apiClient.getCurrentUserId() : apiClient._serverInfo?.UserId;
            if (!userId) { throw new Error("无法获取 UserId"); }
            return await apiClient.getItem(userId, itemId);
        } catch (error) {
            console.error('[Emby工具集] API请求失败:', error);
            return null;
        }
    }

    async function handleWebhookClick(eventName, buttonElement) {
        const originalButtonText = buttonElement.innerHTML;
        const itemId = extractItemIdFromUrl();
        if (!itemId) return;

        // --- 逻辑判断与弹窗确认区 ---

        // 1. 删除功能的确认
        if (eventName === 'delete_override') {
            const confirmed = await showCustomConfirm(
                '您确定要删除此项目的 Override 数据吗？\n此操作通常不可逆！'
            );
            if (!confirmed) return;
        }

        // 2. 高级截图功能的确认
        if (eventName === 'advanced_screenshot') {
            const msg = `
                <strong>📷 准备执行随机截图生成封面</strong>
                <hr style="border:0; border-top:1px solid #eee; margin: 10px 0;">
                ⚠️ <strong>注意：</strong>此功能仅适用于 <span style="color:#E6A23C; font-weight:bold;">单集 (Episode)</span>。<br>
                <br>
                系统将随机截取当前集的一张画面作为封面。<br>
                如果是电影或剧集层级，请勿操作。
            `;
            const confirmed = await showCustomConfirm(msg, '生成截图', '#E6A23C');
            if (!confirmed) return;
        }

        // --- 执行发送逻辑 ---

        buttonElement.innerHTML = '请求API...';
        buttonElement.disabled = true;

        const item = await getMediaItemFromApi(itemId);

        if (!item) {
            showToastNotification('通过API获取媒体信息失败！', 'error');
            buttonElement.innerHTML = 'API失败';
            setTimeout(() => { buttonElement.innerHTML = originalButtonText; buttonElement.disabled = false; }, 3000);
            return;
        }

        const providerIds = item.ProviderIds || {};
        
        let requestBodyString = JSON.stringify(WEBHOOK_DATA_STRUCTURE)
            .replace('"{{event_name}}"', JSON.stringify(eventName))
            .replace('"{{itemId}}"', JSON.stringify(item.Id || itemId))
            .replace('"{{itemType}}"', JSON.stringify(item.Type || "Unknown"))
            .replace('"{{itemName}}"', JSON.stringify(item.Name || ""))
            .replace('"{{tmdbId}}"', JSON.stringify(providerIds.Tmdb || ""))
            .replace('"{{imdbId}}"', JSON.stringify(providerIds.Imdb || ""))
            .replace('"{{tvdbId}}"', JSON.stringify(providerIds.Tvdb || ""));
        const requestBody = JSON.parse(requestBodyString);

        console.log(`[Emby工具集] 准备发送事件 '${eventName}'`, requestBody);
        buttonElement.innerHTML = '发送中...';

        // ============================================
        // 核心修改：使用原生 fetch 替代 GM_xmlhttpRequest
        // ============================================
        fetch(WEBHOOK_URL, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(requestBody) // fetch 使用 body，不是 data
        })
        .then(async response => {
            if (response.ok) {
                showToastNotification(`指令 '${eventName}' 发送成功！`, 'success');
                buttonElement.innerHTML = originalButtonText;
                buttonElement.disabled = false;
            } else {
                throw new Error(`HTTP Status: ${response.status}`);
            }
        })
        .catch(error => {
            console.error("Webhook 发送失败:", error);
            showToastNotification(`指令 '${eventName}' 发送失败！`, 'error');
            buttonElement.innerHTML = '发送失败';
            setTimeout(() => { buttonElement.innerHTML = originalButtonText; buttonElement.disabled = false; }, 3000);
        });
        // ============================================
    }


    // --- 按钮配置与创建 ---
    function createOrUpdateAllButtons() {
        const BUTTON_IDS = {
            DELETE: 'emby-toolkit-delete-btn',
            SCREENSHOT: 'emby-toolkit-screenshot-btn',
            SUPPLEMENT: 'emby-toolkit-supplement-btn',
            DOWNLOAD: 'emby-toolkit-download-btn'
        };

        const baseStyle = {
            position: 'fixed', bottom: '20px', zIndex: '9999', padding: '10px 15px',
            color: 'white', border: 'none', borderRadius: '5px', cursor: 'pointer',
            fontSize: '14px', boxShadow: '0 2px 5px rgba(0,0,0,0.3)', transition: 'all 0.3s'
        };

        const buttonConfigs = [
            { id: BUTTON_IDS.DELETE, text: '🗑️ 删除Override', color: '#F44336', right: '20px', event: 'delete_override' },
            { id: BUTTON_IDS.SUPPLEMENT, text: '➕ 补充到Override', color: '#2196F3', right: '335px', event: 'supplement_to_override' },
            { id: BUTTON_IDS.SCREENSHOT, text: '📷 高级截图', color: '#E6A23C', right: '185px', event: 'advanced_screenshot' },
            { id: BUTTON_IDS.DOWNLOAD, text: '💾 下载图片到Override', color: '#4CAF50', right: '535px', event: 'download_to_override' }
        ];

        let allButtons = [];

        buttonConfigs.forEach(config => {
            let button = document.getElementById(config.id);
            if (!button) {
                button = document.createElement('button');
                button.id = config.id;
                button.innerHTML = config.text;
                Object.assign(button.style, baseStyle, { right: config.right, backgroundColor: config.color });

                if (config.event) {
                    button.addEventListener('click', () => handleWebhookClick(config.event, button));
                }
                document.body.appendChild(button);
            }
            allButtons.push(button);
        });

        const currentItemId = extractItemIdFromUrl();
        allButtons.forEach(btn => {
            if (btn) {
                btn.style.display = currentItemId ? 'block' : 'none';
            }
        });
    }

    // --- 脚本启动逻辑 ---
    function init() {
        setTimeout(() => {
            createOrUpdateAllButtons();
            let lastUrl = window.location.href;
            setInterval(() => {
                if (window.location.href !== lastUrl) {
                    lastUrl = window.location.href;
                    createOrUpdateAllButtons();
                }
            }, 1000);
        }, 2000);
    }

    // --- 存储信息查询功能 ---
    async function queryStorageInfo(embyItemId) {
        try {
            console.log('[存储信息] 开始查询，Emby ID:', embyItemId);
            
            const apiClient = getApiClient();
            if (!apiClient) {
                console.log('[存储信息] 无法获取API客户端，跳过查询');
                return null;
            }
            
            // 使用Emby API获取项目详情
            const itemDetails = await apiClient.getItem(apiClient.getCurrentUserId(), embyItemId);
            console.log('[存储信息] 获取到的项目详情:', itemDetails);
            
            if (!itemDetails) {
                console.log('[存储信息] 无法获取项目详情');
                return null;
            }
            
            // 构造webhook payload
            const payload = {
                "Event": "query_storage",
                "Item": itemDetails
            };
            
            console.log('[存储信息] 发送webhook请求');
            
            const response = await fetch(WEBHOOK_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
            
            console.log('[存储信息] API响应状态:', response.status);
            
            if (!response.ok) {
                console.log('[存储信息] 查询失败，状态:', response.status);
                return null;
            }
            
            const data = await response.json();
            console.log('[存储信息] 获取到的存储信息:', data);
            return data;
        } catch (error) {
            console.error('[存储信息] 查询失败:', error);
            return null;
        }
    }

    function showStoragePanel(storageInfo) {
        const panelId = 'emby-storage-panel';
        const existingPanel = document.getElementById(panelId);
        
        // 如果面板已存在，只更新内容
        if (existingPanel) {
            const contentDiv = existingPanel.querySelector('.storage-panel-content');
            if (contentDiv) {
                contentDiv.innerHTML = generateStorageContent(storageInfo);
            }
            return;
        }

        if (!storageInfo) {
            return;
        }

        const panel = document.createElement('div');
        panel.id = panelId;
        panel.innerHTML = `
            <div style="position: fixed; top: 80px; right: 20px; z-index: 9998; 
                        padding: 15px; background: rgba(255,255,255,0.98); border-radius: 10px; 
                        box-shadow: 0 4px 20px rgba(0,0,0,0.15); max-width: 800px; 
                        max-height: 80vh; overflow-y: auto;">
                <div style="display: flex; justify-content: space-between; align-items: center; 
                           margin-bottom: 12px; border-bottom: 3px solid #4CAF50; padding-bottom: 8px;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <button id="storage-panel-toggle" 
                                style="background: #4CAF50; color: white; border: none; border-radius: 4px; 
                                       width: 28px; height: 28px; cursor: pointer; font-size: 16px; 
                                       display: flex; align-items: center; justify-content: center;">
                            ${STORAGE_PANEL_DEFAULT_EXPANDED ? '▼' : '▶'}
                        </button>
                        <div style="font-weight: bold; color: #333; font-size: 16px;">
                            📦 存储信息
                        </div>
                    </div>
                    <button onclick="document.getElementById('emby-storage-panel').remove()" 
                            style="background: #F44336; color: white; border: none; border-radius: 50%; 
                                   width: 28px; height: 28px; cursor: pointer; font-size: 16px; 
                                   display: flex; align-items: center; justify-content: center;">
                        ✕
                    </button>
                </div>
                <div class="storage-panel-content" 
                     style="display: ${STORAGE_PANEL_DEFAULT_EXPANDED ? 'block' : 'none'};">
                    ${generateStorageContent(storageInfo)}
                </div>
            </div>
        `;
        
        document.body.appendChild(panel);
        
        // 绑定折叠/展开事件
        const toggleBtn = panel.querySelector('#storage-panel-toggle');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => {
                const contentDiv = panel.querySelector('.storage-panel-content');
                if (contentDiv) {
                    if (contentDiv.style.display === 'none') {
                        contentDiv.style.display = 'block';
                        toggleBtn.textContent = '▼';
                    } else {
                        contentDiv.style.display = 'none';
                        toggleBtn.textContent = '▶';
                    }
                }
            });
        }
    }

    function generateStorageContent(storageInfo) {
        const overrideExists = storageInfo.override_cache_exists;
        const primaryConfigured = storageInfo.primary_cache_configured;
        const overrideConfigured = storageInfo.override_cache_configured;
        const images = storageInfo.images || [];
        const seasons = storageInfo.seasons || [];
        const episodeGroupExists = storageInfo.override_episodegroup_exists;
        const episodeOrderExists = storageInfo.override_episodeorder_exists;
        const externalIdsExists = storageInfo.override_externalids_exists;
const patchesExists = storageInfo.override_patches_exists;
        const tags = storageInfo.tags || [];
        
        const overrideStatus = overrideExists ? '✓ 存在' : '✗ 不存在';
        const primaryStatus = primaryConfigured ? '✓ 已配置' : '✗ 未配置';
        const overrideConfigStatus = overrideConfigured ? '✓ 已配置' : '✗ 未配置';

        let imagesHtml = '';
        if (images.length > 0) {
            imagesHtml = images.map(img => `
                <div style="padding: 4px 0; border-bottom: 1px solid #eee;">
                    <span style="color: #666;">${img.label}:</span> 
                    <span style="color: #2196F3;">${img.name}</span>
                </div>
            `).join('');
        } else {
            imagesHtml = '<div style="color: #999; padding: 4px 0;">暂无图片</div>';
        }

        let seasonsHtml = '';
        if (seasons.length > 0) {
            seasonsHtml = seasons.map((season, index) => {
                const stats = season.episode_stats || { total: 0, override: 0, primary: 0 };
                const seasonName = season.name || '';
                const episodes = season.episodes || [];
                
                let episodesHtml = '';
                if (episodes.length > 0) {
                    episodesHtml = episodes.map(ep => {
                        const isOverride = ep.source === 'override';
                        const bgColor = isOverride ? '#4CAF50' : '#f5f5f5';
                        const textColor = isOverride ? '#fff' : '#333';
                        return `
                            <div style="display: inline-block; padding: 4px 8px; margin: 2px; 
                                       background: ${bgColor}; color: ${textColor}; 
                                       border-radius: 4px; font-size: 12px;">
                                E${ep.episode_number}
                            </div>
                        `;
                    }).join('');
                }
                
                return `
                    <div style="margin-bottom: 10px; border: 1px solid #e0e0e0; border-radius: 6px; overflow: hidden;">
                        <div style="padding: 8px 12px; background: #f9f9f9; cursor: pointer; 
                                   display: flex; justify-content: space-between; align-items: center;"
                             onclick="toggleSeasonEpisodes(${index})">
                            <span style="font-weight: bold; color: #333;">
                                S${season.season_number} ${seasonName}
                            </span>
                            <span style="font-size: 12px; color: #666;">
                                总计: ${stats.total} | Override: ${stats.override} | 主缓存: ${stats.primary}
                                <span id="season-arrow-${index}" style="margin-left: 8px;">▼</span>
                            </span>
                        </div>
                        <div id="season-episodes-${index}" style="display: none; padding: 8px 12px;">
                            ${episodesHtml}
                        </div>
                    </div>
                `;
            }).join('');
        } else {
            seasonsHtml = '<div style="color: #999; padding: 4px 0;">暂无季度信息</div>';
        }

        let tagsHtml = '';
        if (tags.length > 0) {
            tagsHtml = tags.map(tag => `
                <span style="display: inline-block; padding: 3px 8px; margin: 2px; 
                          background: #E3F2FD; color: #1976D2; border-radius: 4px; font-size: 12px;">
                    ${tag}
                </span>
            `).join('');
        } else {
            tagsHtml = '<span style="color: #999; font-size: 12px;">暂无标签</span>';
        }

        return `
                <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                    <div style="flex: 1; min-width: 300px;">
                        <div style="display: flex; gap: 10px; margin-bottom: 10px;">
                            <div style="flex: 1; padding: 8px; background: #f5f5f5; border-radius: 6px;">
                                <div style="font-weight: bold; color: #333; margin-bottom: 4px;">Override缓存</div>
                                <div style="color: ${overrideExists ? '#4CAF50' : '#F44336'};">${overrideStatus}</div>
                            </div>
                            <div style="flex: 1; padding: 8px; background: #f5f5f5; border-radius: 6px;">
                                <div style="font-weight: bold; color: #333; margin-bottom: 4px;">主缓存配置</div>
                                <div style="color: ${primaryConfigured ? '#4CAF50' : '#F44336'};">${primaryStatus}</div>
                            </div>
                        </div>
                        <div style="padding: 8px; background: #f5f5f5; border-radius: 6px; margin-bottom: 10px;">
                            <div style="font-weight: bold; color: #333; margin-bottom: 4px;">Override配置</div>
                            <div style="color: ${overrideConfigured ? '#4CAF50' : '#F44336'};">${overrideConfigStatus}</div>
                        </div>
                        
                        <div style="margin-top: 15px; font-weight: bold; color: #333; 
                                   border-bottom: 2px solid #FF9800; padding-bottom: 6px; margin-bottom: 8px;">
                            📁 特殊文件
                        </div>
                        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-bottom: 15px;">
                            <div style="padding: 6px; background: #f9f9f9; border-radius: 4px; font-size: 12px;">
                                <span style="color: #666;">剧集组:</span> 
                                <span style="color: ${episodeGroupExists ? '#4CAF50' : '#999'}; font-weight: bold;">
                                    ${episodeGroupExists ? '✓ 存在' : '✗ 不存在'}
                                </span>
                            </div>
                            <div style="padding: 6px; background: #f9f9f9; border-radius: 4px; font-size: 12px;">
                                <span style="color: #666;">插入:</span> 
                                <span style="color: ${episodeOrderExists ? '#4CAF50' : '#999'}; font-weight: bold;">
                                    ${episodeOrderExists ? '✓ 存在' : '✗ 不存在'}
                                </span>
                            </div>
                            <div style="padding: 6px; background: #f9f9f9; border-radius: 4px; font-size: 12px;">
                                <span style="color: #666;">外部ID:</span> 
                                <span style="color: ${externalIdsExists ? '#4CAF50' : '#999'}; font-weight: bold;">
                                    ${externalIdsExists ? '✓ 存在' : '✗ 不存在'}
                                </span>
                            </div>
                            <div style="padding: 6px; background: #f9f9f9; border-radius: 4px; font-size: 12px;">
                                <span style="color: #666;">Patches:</span> 
                                <span style="color: ${patchesExists ? '#4CAF50' : '#999'}; font-weight: bold;">
                                    ${patchesExists ? '✓ 存在' : '✗ 不存在'}
                                </span>
                            </div>
                        </div>
                        
                        <div style="margin-top: 15px; font-weight: bold; color: #333; 
                                   border-bottom: 2px solid #9C27B0; padding-bottom: 6px; margin-bottom: 8px;">
                            🏷️ 标签
                        </div>
                        <div style="margin-bottom: 15px;">
                            ${tagsHtml}
                        </div>
                        
                        <div style="margin-top: 15px; font-weight: bold; color: #333; 
                                   border-bottom: 2px solid #2196F3; padding-bottom: 6px; margin-bottom: 8px;">
                            📷 图片 (${images.length}张)
                        </div>
                        <div>
                            ${imagesHtml}
                        </div>
                    </div>
                    
                    <div style="flex: 1; min-width: 300px;">
                        <div style="margin-top: 0; font-weight: bold; color: #333; 
                                   border-bottom: 2px solid #FF9800; padding-bottom: 6px; margin-bottom: 8px;">
                            📺 剧集信息 (${seasons.length}季)
                        </div>
                        <div style="max-height: 300px; overflow-y: auto;">
                            ${seasonsHtml}
                        </div>
                    </div>
                </div>
        `;
    }

    window.toggleSeasonEpisodes = function(seasonIndex) {
        const episodesDiv = document.getElementById(`season-episodes-${seasonIndex}`);
        const arrowSpan = document.getElementById(`season-arrow-${seasonIndex}`);
        
        if (episodesDiv) {
            if (episodesDiv.style.display === 'none') {
                episodesDiv.style.display = 'block';
                arrowSpan.textContent = '▲';
            } else {
                episodesDiv.style.display = 'none';
                arrowSpan.textContent = '▼';
            }
        }
    };

    // --- 修改init函数，添加存储信息查询 ---
    const originalInit = init;
    init = function() {
        originalInit();
        
        // 添加存储信息查询
        if (ENABLE_STORAGE_INFO) {
            // 定义查询存储信息的函数
            const queryAndShowStorage = function() {
                const currentItemId = extractItemIdFromUrl();
                if (currentItemId) {
                    queryStorageInfo(currentItemId).then(storageInfo => {
                        showStoragePanel(storageInfo);
                    });
                } else {
                    // 没有项目ID时隐藏面板
                    const panel = document.getElementById('emby-storage-panel');
                    if (panel) panel.remove();
                }
            };
            
            // 初始查询
            setTimeout(queryAndShowStorage, 3000);
            
            // 监听URL变化
            let lastUrl = window.location.href;
            setInterval(() => {
                if (window.location.href !== lastUrl) {
                    lastUrl = window.location.href;
                    queryAndShowStorage();
                }
            }, 1000);
        }
    };

    init();
})();