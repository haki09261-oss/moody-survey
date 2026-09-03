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
    assert "onchange=applyFilters" in response.text
    assert "refreshDashboardData" in response.text
    assert "dashboardRequestId" in response.text
    assert "filterOperationId" in response.text
    assert "loadOperationId" in response.text
    assert 'id="loginButton"' in response.text
    assert "正在登录并加载" in response.text
    assert "submissions/summary" in response.text
    assert "if(!state.searchTerm)submissionParams.set('limit','100')" in response.text
    assert "state.rows=[];state.summary=null;state.dashboardStatus='loading'" in response.text
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
