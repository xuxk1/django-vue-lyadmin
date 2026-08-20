<template>
    <div>
        <ly-dialog v-model="dialogVisible" :title="dialogTitle" width="640px" :before-close="handleClose">
            <el-form :inline="false" :model="formData" :rules="rules" ref="rulesForm" label-position="right" label-width="auto" class="form-store">
                <el-form-item label="父级部门：" prop="parent">
                    <el-tree-select v-model="formData.parent" node-key="id" :data="options"
                            check-strictly filterable clearable :render-after-expand="false"
                            :props="{label:'name',value: 'id'}"
                            style="width: 100%" placeholder="请选择/为空则为顶级" />
                </el-form-item>
                <el-form-item label="部门名称：" prop="name">
                    <el-input v-model.trim="formData.name"></el-input>
                </el-form-item>
                <el-form-item label="负责人：" prop="owner">
                    <el-select v-model="formData.owner" filterable remote clearable :remote-method="searchUsers"
                            :reserve-keyword="false" placeholder="输入姓名/账号搜索选择用户" style="width: 100%">
                        <el-option v-for="u in userOptions" :key="u.value" :label="u.label" :value="u.value"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="联系电话：" prop="phone">
                    <el-input v-model.trim="formData.phone"></el-input>
                </el-form-item>
                <el-form-item label="邮箱：" prop="email">
                    <el-input v-model.trim="formData.email"></el-input>
                </el-form-item>
                <el-form-item label="状态：" prop="status">
                    <el-radio-group v-model="formData.status">
                        <el-radio :value="1">启用</el-radio>
                        <el-radio :value="0">禁用</el-radio>
                    </el-radio-group>
                </el-form-item>
                <el-form-item label="排序：" prop="sort">
                    <el-input-number v-model="formData.sort" :min="0" :max="999999"></el-input-number>
                </el-form-item>

            </el-form>
            <template #footer>
                <el-button @click="handleClose" :loading="loadingSave">取消</el-button>
                <el-button type="primary" @click="submitData" :loading="loadingSave" v-if="dialogTitle!='详情'">确定</el-button>
            </template>
        </ly-dialog>
    </div>
</template>

<script>
    import utils from '@/utils/util'
    import {apiSystemDeptAdd,apiSystemDept,apiSystemDeptEdit,apiSystemAllUser} from '@/api/api'
    import LyDialog from "@/components/dialog/dialog";
    import {deepClone} from "@/utils/util";
    import XEUtils from "xe-utils";
    export default {
        components: {LyDialog},
        emits: ['refreshData'],
        name: "addDepartment",
        data() {
            return {
                dialogVisible:false,
                loadingSave:false,
                dialogTitle:'',
                isResourceShow:0,
                formData:{
                    parent:'',
                    name:'',
                    phone:'',
                    owner:'',
                    status:1,
                    sort:0,
                },
                rules:{
                    // parent: [
                    //     {required: true, message: '请选择父级菜单',trigger: 'blur'}
                    // ],
                    name: [
                        {required: true, message: '请输入部门名称',trigger: 'blur'}
                    ],
                    // phone: [
                    //     {required: true, message: '请输入联系电话',trigger: 'blur'}
                    // ],
                    // owner: [
                    //     {required: true, message: '请输入负责人',trigger: 'blur'}
                    // ],
                    status: [
                        {required: true, message: '请选择状态',trigger: 'blur'}
                    ],
                    // sort: [
                    //     {required: true, message: '请输入排序',trigger: 'blur'}
                    // ],
                },
                options: [],
                userOptions: []
            }
        },
        methods:{
            handleClose() {
                this.dialogVisible=false
                this.loadingSave=false
                this.userOptions = []
                this.formData = {
                    parent:'',
                    name:'',
                    phone:'',
                    owner:'',
                    status:1,
                    sort:0,
                }
            },
            addDepartmentFn(item,flag) {
                this.dialogVisible=true
                this.dialogTitle=flag
                this.options=[]
                if(item){
                    this.formData = deepClone(item)
                }
                // 负责人回显：存量数据为姓名文本，直接作为选项值保证选中框正常显示
                if (this.formData.owner && !this.userOptions.find(o => o.value === this.formData.owner)) {
                    this.userOptions.push({value: this.formData.owner, label: this.formData.owner})
                }
                this.getapiSystemDept()
            },
            submitData() {
                this.$refs['rulesForm'].validate(obj=>{
                    if(obj) {
                        this.loadingSave=true
                        let param = {
                            ...this.formData
                        }
                        if( typeof param.parent== 'object') {
                            param.parent = this.formData.parent ?  this.formData.parent[this.formData.parent.length-1] : ''
                        }else if(param.parent == null ||param.parent == undefined){
                            param.parent = ""
                        }
                        // 负责人清空后 el-select 值为 undefined，JSON 序列化会丢弃该字段导致后端不更新，归一为空字符串
                        param.owner = param.owner || ''
                        if(this.formData.id){
                            apiSystemDeptEdit(param).then(res=>{
                                this.loadingSave=false
                                if(res.code == 2000) {
                                    this.$message.success(res.msg)
                                    this.handleClose()
                                    this.$emit('refreshData')
                                } else {
                                    this.$message.warning(res.msg)
                                }
                            })
                        }else{
                            apiSystemDeptAdd(param).then(res=>{
                                this.loadingSave=false
                                if(res.code == 2000) {
                                    this.$message.success(res.msg)
                                    this.handleClose()
                                    this.$emit('refreshData')
                                } else {
                                    this.$message.warning(res.msg)
                                }
                            })
                        }
                    }
                })
            },
            getapiSystemDept() {
                var params = {
                    page:1,
                    limit:9999
                }
                apiSystemDept(params).then(res=>{
                    if(res.code == 2000) {
                        this.options = XEUtils.toArrayTree(res.data.data, { parentKey: 'parent' })
                    } else {
                        this.$message.warning(res.msg)
                    }
                })
            },
            // 远程搜索用户（姓名/账号联想），选中后写入负责人姓名（与存量数据格式一致）
            searchUsers(query) {
                if (!query) return
                apiSystemAllUser({search: query, page: 1, limit: 20}).then(res => {
                    if (res.code === 2000) {
                        const list = (res.data.data || []).map(u => ({
                            value: u.name || u.username,
                            label: u.name ? `${u.name}(${u.username})` : u.username
                        }))
                        list.forEach(u => {
                            if (!this.userOptions.find(o => o.value === u.value)) {
                                this.userOptions.push(u)
                            }
                        })
                    }
                }).catch(() => {})
            }
        }
    }
</script>

