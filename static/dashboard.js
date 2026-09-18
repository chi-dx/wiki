const layers = [
  {name:'数据接入', caption:'INGESTION', items:[
    {name:'Kafka', icon:'KF', score:9.1, level:'领先', color:'blue', metrics:[['吞吐提升','32%'],['P99 延迟','-18%'],['资源效率','1.24×']], note:'在高并发顺序写入场景表现突出，NUMA 亲和优化后吞吐优势明显。'},
    {name:'Flink CDC', icon:'FC', score:8.4, level:'优势', color:'cyan', metrics:[['同步吞吐','21 万行/s'],['延迟','1.8 s'],['稳定性','99.95%']], note:'适合数据库增量同步；宽表合并场景仍有进一步调优空间。'},
    {name:'Logstash', icon:'LS', score:6.8, level:'劣势', color:'violet', metrics:[['采集速率','8.6 TB/d'],['CPU 开销','+12%'],['丢包率','0.01%']], note:'通用日志采集功能稳定，但复杂正则解析的 CPU 开销偏高，是当前主要性能短板。'},
    {name:'Apache SeaTunnel', icon:'ST', score:8.7, level:'优势', color:'blue', metrics:[['同步吞吐','+24%'],['连接器','160+'],['资源效率','1.18×']], note:'批流一体的数据集成场景表现均衡，多源异构同步具备较好扩展能力。'},
    {name:'Filebeat', icon:'FB', score:7.8, level:'持平', color:'cyan', metrics:[['采集吞吐','+8%'],['内存占用','-6%'],['端侧开销','中']], note:'轻量日志采集总体与对标平台相当，在超大规模边缘节点上的资源波动仍需观察。'}]},
  {name:'计算与调度', caption:'COMPUTE', items:[
    {name:'Apache Spark', icon:'SP', score:9.3, level:'领先', color:'red', metrics:[['TPC-DS','+28%'],['任务耗时','-22%'],['性价比','1.31×']], note:'向量化执行与大内存带宽场景优势突出，是当前重点竞争组件。'},
    {name:'Apache Flink', icon:'FL', score:8.9, level:'领先', color:'blue', metrics:[['流处理吞吐','+25%'],['Checkpoint','-17%'],['反压恢复','42 s']], note:'流式计算性能突出，状态后端调优后大状态任务恢复速度显著改善。'},
    {name:'Apache Airflow', icon:'AF', score:7.7, level:'持平', color:'cyan', metrics:[['调度容量','5 万任务/d'],['启动延迟','-4%'],['可用性','99.97%']], note:'调度和控制面稳定，综合表现与对标平台相当，海量短任务场景的数据库压力需要重点关注。'},
    {name:'Apache Hive', icon:'HV', score:8.5, level:'优势', color:'violet', metrics:[['批处理性能','+22%'],['Tez 任务','-16%'],['并发能力','+14%']], note:'传统离线数仓场景成熟稳定，执行引擎和文件格式联合调优后优势明显。'}]},
  {name:'数据存储', caption:'STORAGE', items:[
    {name:'HDFS', icon:'HD', score:9.0, level:'领先', color:'blue', metrics:[['顺序读','+29%'],['顺序写','+24%'],['磁盘利用率','86%']], note:'顺序读写和多副本复制性能较强，适合大规模离线数据湖。'},
    {name:'HBase', icon:'HB', score:8.6, level:'优势', color:'red', metrics:[['随机读','+19%'],['写入吞吐','+23%'],['P99 延迟','7.4 ms']], note:'高并发写入竞争力较好，热点 Region 场景需结合预分区策略。'},
    {name:'ClickHouse', icon:'CH', score:9.4, level:'领先', color:'violet', metrics:[['聚合查询','+36%'],['压缩率','4.8×'],['并发查询','+27%']], note:'分析型负载综合表现最佳，列式扫描和并行聚合充分利用鲲鹏多核能力。'},
    {name:'Apache Iceberg', icon:'IB', score:8.8, level:'领先', color:'cyan', metrics:[['表扫描','+25%'],['提交延迟','-19%'],['元数据量','千万级']], note:'数据湖表格式在大分区和增量扫描中表现突出，适合湖仓一体架构。'},
    {name:'Apache Doris', icon:'DO', score:9.0, level:'领先', color:'blue', metrics:[['即席查询','+30%'],['导入吞吐','+21%'],['并发查询','+24%']], note:'实时分析和高并发报表性能较强，向量化计算能发挥多核优势。'},
    {name:'Ceph', icon:'CP', score:7.9, level:'持平', color:'red', metrics:[['对象吞吐','+7%'],['恢复速度','+5%'],['可用性','99.99%']], note:'分布式对象存储稳定性良好，综合表现与对标平台相当，小对象密集场景仍需专项调优。'}]},
  {name:'数据服务', caption:'SERVING', items:[
    {name:'Trino', icon:'TR', score:8.8, level:'领先', color:'violet', metrics:[['联邦查询','+26%'],['并发用户','180'],['P95 延迟','-20%']], note:'跨源查询与高并发分析有明显优势，复杂 Join 仍受网络交换效率影响。'},
    {name:'Elasticsearch', icon:'ES', score:8.2, level:'优势', color:'cyan', metrics:[['索引吞吐','+18%'],['检索延迟','-15%'],['节点密度','+12%']], note:'检索和写入均衡，推荐结合堆外内存与分片规模进行专项调优。'},
    {name:'Redis', icon:'RD', score:9.2, level:'领先', color:'red', metrics:[['QPS','+31%'],['P99 延迟','0.72 ms'],['能效','+20%']], note:'内存访问和多核扩展表现突出，适合作为实时特征与热点数据服务。'}]}
];

const simpleIcon = slug => `https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/${slug}.svg`;
const logos = {
  'Kafka': simpleIcon('apachekafka'),
  'Flink CDC': simpleIcon('apacheflink'),
  'Logstash': simpleIcon('logstash'),
  'Apache SeaTunnel': 'https://www.apache.org/logos/res/seatunnel/default.png',
  'Filebeat': simpleIcon('elasticsearch'),
  'Apache Spark': simpleIcon('apachespark'),
  'Apache Flink': simpleIcon('apacheflink'),
  'Apache Airflow': simpleIcon('apacheairflow'),
  'Apache Hive': simpleIcon('apachehive'),
  'HDFS': simpleIcon('apachehadoop'),
  'HBase': simpleIcon('apachehbase'),
  'ClickHouse': simpleIcon('clickhouse'),
  'Apache Iceberg': 'https://www.apache.org/logos/res/iceberg/default.png',
  'Apache Doris': 'https://www.apache.org/logos/res/doris/default.png',
  'Ceph': simpleIcon('ceph'),
  'Trino': simpleIcon('trino'),
  'Elasticsearch': simpleIcon('elasticsearch'),
  'Redis': simpleIcon('redis')
};

const landscape = document.querySelector('#landscape');
const detail = document.querySelector('#detail');
const levelClass = level => ({'领先':'leading','优势':'advantage','持平':'even','劣势':'weak'}[level] || 'even');

function showDetail(item, button) {
  document.querySelectorAll('.component.selected').forEach(el=>el.classList.remove('selected'));
  button.classList.add('selected');
  const logoClass = logos[item.name].includes('jsdelivr') ? `mono ${item.color}` : '';
  detail.innerHTML = `<div class="detail-top"><span class="component-icon logo ${logoClass}"><img src="${logos[item.name]}" alt=""><b>${item.icon}</b></span><div><small>COMPONENT PROFILE</small><h2>${item.name}</h2></div></div><div class="score"><div><span>性能竞争力</span><strong>${item.score}</strong><small>/ 10</small></div><em class="${levelClass(item.level)}">${item.level}</em></div><div class="meter"><i style="width:${item.score * 10}%"></i></div><div class="metrics">${item.metrics.map(([key,value])=>`<div><span>${key}</span><b>${value}</b></div>`).join('')}</div><p class="assessment">${item.note}</p><p class="fiction">演示评估数据</p>`;
  const detailLogo = detail.querySelector('.component-icon img');
  detailLogo.addEventListener('error',()=>{ detailLogo.hidden = true; detail.querySelector('.component-icon b').hidden = false; });
  detail.classList.add('has-selection');
  detail.scrollIntoView({behavior:'smooth', block:'center'});
}

for (const layer of layers) {
  const section = document.createElement('section'); section.className = 'layer';
  section.innerHTML = `<header><span>${layer.caption}</span><h2>${layer.name}</h2></header>`;
  const items = document.createElement('div'); items.className = 'components';
  for (const item of layer.items) {
    const button = document.createElement('button'); button.className = 'component'; button.type = 'button';
    button.setAttribute('aria-label', `${item.name}，性能竞争力 ${item.score}`);
    const logoClass = logos[item.name].includes('jsdelivr') ? `mono ${item.color}` : '';
    button.innerHTML = `<span class="component-icon logo ${logoClass}"><img src="${logos[item.name]}" alt=""><b>${item.icon}</b></span><span class="component-name">${item.name}</span><span class="status ${levelClass(item.level)}">${item.level}</span><span class="tooltip"><b>性能竞争力 ${item.score}</b><small>${item.metrics[0][0]} ${item.metrics[0][1]}</small><i>点击查看详情</i></span>`;
    const logo = button.querySelector('.component-icon img');
    logo.addEventListener('error',()=>{ logo.hidden = true; button.querySelector('.component-icon b').hidden = false; });
    button.addEventListener('click',()=>showDetail(item,button)); items.append(button);
  }
  section.append(items); landscape.append(section);
}
