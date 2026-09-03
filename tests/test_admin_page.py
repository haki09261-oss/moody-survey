def test_admin_page_uses_dashboard_layout(client):
    response = client.get("/admin")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert "问卷数据与兑奖后台" in response.text
    assert 'class="stats"' in response.text
    assert "每日答卷趋势" in response.text
    assert "异常原因分布" in response.text
    assert "每道题选项占比" in response.text
    assert "答卷明细与兑奖操作" in response.text
    assert "匿名参与标识" in response.text
    assert "删除测试答卷" in response.text
    assert "/purge" in response.text
    assert "questionStatsQuery" in response.text
    assert "status',status" in response.text
    assert "scope',scope" in response.text
    assert "days',days" in response.text
    assert "onchange=()=>applyFilters()" in response.text
    assert "refreshDashboardData" in response.text
    assert "dashboardRequestId" in response.text
    assert "filterOperationId" in response.text
    assert "loadOperationId" in response.text
    assert 'id="loginButton"' in response.text
    assert "正在登录并加载" in response.text
    assert "submissions/summary" in response.text
    assert "submissionQuery=dataQuery(true,true)" in response.text
    assert "state.rows=[];state.total=0;state.summary=null;state.dashboardStatus='loading'" in response.text
    assert "state.dashboardStatus='error';state.dashboardError=error.message;state.questionsStatus='error'" in response.text
    assert "operationId!==loadOperationId" in response.text
    assert "if(event.key==='Enter')applyFilters()" in response.text
    assert "new AbortController()" in response.text
    assert "请求超时，请稍后重试" in response.text
    assert "逐题统计加载中" in response.text
    assert "打开未提交" in response.text
    assert "导出中" in response.text
    assert "refreshQuestionStats" in response.text
    assert "refreshOpened" in response.text


def test_admin_page_uses_server_search_and_real_pagination(client):
    response = client.get("/admin")
    html = response.text

    assert response.status_code == 200
    assert 'placeholder="#提交ID、完整兑换码或完整参与标识"' in html
    assert '<option value="">分析中的答卷</option>' in html
    assert '<option value="all">全部记录</option>' in html
    assert '<option value="rejected">已拒绝</option>' in html
    assert '<option value="in_progress">未完成</option>' in html
    assert 'id="pageInfo"' in html
    assert 'id="prevPage"' in html
    assert 'id="nextPage"' in html
    assert "params.set('search',state.searchTerm)" in html
    assert "params.set('limit',String(state.pageSize))" in html
    assert "params.set('offset',String(state.offset))" in html
    assert "state.searchTerm=$('#search').value.trim().toUpperCase();state.offset=0" in html
    assert "$('#prevPage').onclick=()=>changePage(-1)" in html
    assert "$('#nextPage').onclick=()=>changePage(1)" in html
    assert "dataQuery(false,true)" in html
    assert "new URLSearchParams({only_unsubmitted:'true',limit:'1'})" in html
    assert "state.openedTotal=Number(opened.total??state.opened.length)" in html
    assert "const visible=rows;" in html
    assert "matchesSearch" not in html
    assert "filteredRows" not in html
    assert "slice(0,100)" not in html
